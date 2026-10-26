"""JSON payloads for the desk, the month score, and the calendar."""

from __future__ import annotations

import math
from datetime import date, datetime, time, timedelta

from backend.analysis import (
    AUCTIONS,
    COMPARE_WITH,
    FIT_UNTIL,
    JANUARY_2026,
    LONDON,
    TEST_FROM,
    Auction,
    actual_hour,
    covers,
    decision_deadline,
    decision_pairs,
    error_model,
    haircut_effect,
    hour_keys,
    iso_z,
    london_clock,
    metric_block,
    parse_utc,
    pearson,
    persistence_forecasts,
    quantile,
    select_publish,
    skill_score,
    slot_pairs_on_decision_day,
)
from backend.store import Snapshot


def auction_public(auction: Auction) -> dict:
    return {
        "id": auction.id,
        "name": auction.name,
        "gate_local": auction.gate_local,
        "product": auction.product,
        "detail": auction.detail,
    }


def meta_payload(snapshot: Snapshot) -> dict:
    return {
        "product": "Windgate",
        "fetched_at": snapshot.meta.get("fetched_at"),
        "window_label": "1–31 January 2026",
        "actual_rows": len(snapshot.actuals),
        "forecast_rows": snapshot.forecast_rows,
        "publications": len(snapshot.publishes),
        "timezone_note": (
            "January 2026 is GMT, so London time and UTC show the same clock. "
            "Gates are still applied in Europe/London."
        ),
        "auctions": [auction_public(auction) for auction in AUCTIONS.values()],
        "sources": snapshot.meta.get("endpoints", []),
    }


def calendar_payload(snapshot: Snapshot, auction: Auction, buffer_min: int) -> dict:
    days = []
    spotlight = None
    for delivery in JANUARY_2026:
        deadline = decision_deadline(delivery, auction, buffer_min)
        publish = select_publish(snapshot.publishes, snapshot.forecasts, delivery, deadline)
        forecast_mwh = _day_mwh(snapshot, publish, delivery) if publish else None
        previous = _previous_publish(snapshot, delivery, deadline, publish) if publish else None
        previous_mwh = _day_mwh(snapshot, previous, delivery) if previous else None
        revision = None
        if forecast_mwh is not None and previous_mwh is not None:
            revision = forecast_mwh - previous_mwh
        local_date, clock = london_clock(publish) if publish else (None, None)
        days.append(
            {
                "delivery": delivery.isoformat(),
                "weekday": delivery.strftime("%A"),
                "weekday_index": delivery.weekday(),
                "day": delivery.day,
                "forecast_mwh": r0(forecast_mwh),
                "revision_mwh": r0(revision),
                "publish_local": clock,
                "publish_date": local_date.isoformat() if local_date else None,
            }
        )
        if delivery.day >= 11 and revision is not None:
            score = abs(revision)
            if spotlight is None or score > spotlight[0] or (score == spotlight[0] and delivery > spotlight[1]):
                spotlight = (score, delivery, revision)
    if spotlight is None:
        chosen = date(2026, 1, 15)
        reason = "Mid-month delivery day."
        moved = None
    else:
        chosen = spotlight[1]
        moved = r0(spotlight[2])
        reason = (
            "Largest move between the last two files available before this gate, "
            "among delivery days from 11 January onward."
        )
    return {
        "auction": auction_public(auction),
        "buffer_min": buffer_min,
        "days": days,
        "spotlight": {
            "delivery": chosen.isoformat(),
            "auction": auction.id,
            "buffer_min": buffer_min,
            "revision_mwh": moved,
            "reason": reason,
        },
    }


def desk_payload(snapshot: Snapshot, delivery: date, auction: Auction, buffer_min: int, context: str) -> dict:
    deadline = decision_deadline(delivery, auction, buffer_min)
    publish = select_publish(snapshot.publishes, snapshot.forecasts, delivery, deadline)
    pairs = decision_pairs(
        snapshot.publishes,
        snapshot.forecasts,
        snapshot.actuals,
        auction,
        buffer_min,
    )
    if context == "prior":
        history = [pair for pair in pairs if pair.delivery < delivery]
        basis = "earlier delivery days in January only"
    else:
        history = list(pairs)
        basis = "all of January, including days after this one"
    model = error_model(history)
    band_public = None
    if model is not None and model.n >= 48:
        band_public = {
            "basis": basis,
            "hours_used": model.n,
            "days_used": model.days,
            "global_bias_mw": r0(model.bias_mw),
            "note": (
                "The band is the 10th to 90th percentile of forecast-minus-actual, "
                "taken inside the forecast-level bin when that bin has at least 24 hours, "
                "otherwise from the whole sample. It describes observed misses. "
                "It is not a weather-model confidence interval."
            ),
        }

    hours = []
    raw_forecasts: list[float] = []
    raw_actuals: list[float] = []
    raw_errors: list[float] = []
    if publish is not None:
        series = snapshot.forecasts[publish]
        for hour_start in _hours(delivery):
            key = iso_z(hour_start)
            forecast_mw = series[key]
            raw_forecasts.append(forecast_mw)
            observed = actual_hour(snapshot.actuals, hour_start)
            debiased = band_low = band_high = None
            if model is not None and model.n >= 48:
                debiased, band_low, band_high = model.apply(forecast_mw)
            actual_mw = error_mw = None
            sp1 = sp2 = None
            if observed is not None:
                sp1, sp2 = observed
                actual_mw = (sp1 + sp2) / 2
                error_mw = forecast_mw - actual_mw
                raw_actuals.append(actual_mw)
                raw_errors.append(error_mw)
            local = hour_start.astimezone(LONDON)
            hours.append(
                {
                    "start_utc": key,
                    "label": local.strftime("%H:%M"),
                    "hour_local": local.hour,
                    "sp_start": _settlement_period(hour_start),
                    "sp_end": _settlement_period(hour_start + timedelta(minutes=30)),
                    "forecast_mw": r0(forecast_mw),
                    "actual_sp1_mw": r0(sp1),
                    "actual_sp2_mw": r0(sp2),
                    "actual_mw": r0(actual_mw),
                    "error_mw": r0(error_mw),
                    "band_low_mw": r0(band_low),
                    "band_high_mw": r0(band_high),
                    "debiased_mw": r0(debiased),
                }
            )

    totals = {
        "forecast_mwh": r0(sum(raw_forecasts)) if raw_forecasts else None,
        "forecast_mean_mw": r0(sum(raw_forecasts) / len(raw_forecasts)) if raw_forecasts else None,
        "forecast_min_mw": r0(min(raw_forecasts)) if raw_forecasts else None,
        "forecast_max_mw": r0(max(raw_forecasts)) if raw_forecasts else None,
        "actual_mwh": r0(sum(raw_actuals)) if raw_actuals else None,
        "error_mwh": r0(sum(raw_errors)) if raw_errors else None,
        "paired_hours": len(raw_actuals),
        "forecast_hours": len(hours),
        "debiased_mwh": r0(sum(hour["debiased_mw"] for hour in hours if hour["debiased_mw"] is not None))
        if hours and all(hour["debiased_mw"] is not None for hour in hours)
        else None,
    }

    vintages = _vintages(snapshot, delivery, deadline, publish)
    previous = _previous_block(vintages, publish)
    comparison = _comparison(snapshot, delivery, auction, buffer_min, totals.get("forecast_mwh"), publish)
    vintage_public = None
    if publish is not None:
        publish_date, clock = london_clock(publish)
        minutes = int(round((deadline - parse_utc(publish)).total_seconds() / 60))
        vintage_public = {
            "publish_utc": publish,
            "publish_local": clock,
            "publish_date": publish_date.isoformat(),
            "publish_date_label": _long_date(publish_date),
            "minutes_before_deadline": minutes,
        }

    narrative = _desk_narrative(
        delivery,
        auction,
        buffer_min,
        vintage_public,
        totals,
        previous,
        comparison,
        band_public,
        context,
    )
    return {
        "delivery": delivery.isoformat(),
        "delivery_label": _long_date(delivery),
        "weekday": delivery.strftime("%A"),
        "auction": auction_public(auction),
        "buffer_min": buffer_min,
        "context": context,
        "deadline_utc": iso_z(deadline),
        "deadline_local": deadline.astimezone(LONDON).strftime("%H:%M"),
        "deadline_date_label": _long_date(deadline.astimezone(LONDON).date()),
        "vintage": vintage_public,
        "hours": hours,
        "totals": totals,
        "vintages": vintages,
        "previous": previous,
        "comparison": comparison,
        "band": band_public,
        "narrative": narrative,
    }


def accuracy_payload(snapshot: Snapshot, auction: Auction, buffer_min: int) -> dict:
    pairs = decision_pairs(
        snapshot.publishes,
        snapshot.forecasts,
        snapshot.actuals,
        auction,
        buffer_min,
    )
    if not pairs:
        return {
            "auction": auction_public(auction),
            "buffer_min": buffer_min,
            "sample": {"hours": 0, "days": 0, "missing_days": [day.isoformat() for day in JANUARY_2026], "missing_hours": 0},
            "narrative": ["No delivery day in January had a full wind file at or before this deadline."],
        }

    forecasts = [pair.forecast_mw for pair in pairs]
    actuals = [pair.actual_mw for pair in pairs]
    block = metric_block(forecasts, actuals)
    errors = [pair.error_mw for pair in pairs]
    persisted, filed, observed = persistence_forecasts(snapshot.actuals, pairs)
    persistence = metric_block(persisted, observed) if persisted else None
    filed_on_same_hours = metric_block(filed, observed) if filed else None
    skill = None
    if persistence and filed_on_same_hours:
        skill = skill_score(filed_on_same_hours["mae_mw"], persistence["mae_mw"])

    spans = [abs(pair.sp1_mw - pair.sp2_mw) for pair in pairs]
    span_mw = sum(spans) / len(spans)
    abs_errors = [abs(error) for error in errors]
    p90_signed = quantile(errors, 0.90)
    bias_effect = haircut_effect(errors, block["bias_mw"])
    p90_effect = haircut_effect(errors, p90_signed)

    fit_pairs = [pair for pair in pairs if pair.delivery <= FIT_UNTIL]
    test_pairs = [pair for pair in pairs if pair.delivery >= TEST_FROM]
    holdout = _holdout(fit_pairs, test_pairs)

    by_day = _by_day(pairs)
    by_hour = _by_hour(pairs)
    by_vintage = _by_vintage(snapshot, auction, buffer_min)
    by_level = _by_level(pairs)
    histogram = _histogram(errors)
    scatter = [
        {"forecast_mw": r0(pair.forecast_mw), "actual_mw": r0(pair.actual_mw)}
        for pair in pairs
    ]
    worst = sorted(by_day, key=lambda row: abs(row["error_mwh"]), reverse=True)[:5]
    missing_days = []
    expected_hours = 0
    for delivery in JANUARY_2026:
        deadline = decision_deadline(delivery, auction, buffer_min)
        publish = select_publish(snapshot.publishes, snapshot.forecasts, delivery, deadline)
        if publish is None:
            missing_days.append(delivery.isoformat())
            continue
        expected_hours += len(hour_keys(delivery))
    missing_hours = expected_hours - len(pairs)

    payload = {
        "auction": auction_public(auction),
        "buffer_min": buffer_min,
        "sample": {
            "hours": len(pairs),
            "days": len({pair.delivery for pair in pairs}),
            "missing_days": missing_days,
            "missing_hours": missing_hours,
            "persistence_hours": len(persisted),
        },
        "forecast": _round_block(block),
        "persistence": _round_block(persistence) if persistence else None,
        "skill_vs_persistence": r4(skill),
        "correlation": r4(pearson(forecasts, actuals)),
        "within_hour_span_mw": r0(span_mw),
        "within_hour_unresolved_mw": r0(span_mw / 2),
        "quantiles_abs_mw": {
            "p50": r0(quantile(abs_errors, 0.50)),
            "p80": r0(quantile(abs_errors, 0.80)),
            "p90": r0(quantile(abs_errors, 0.90)),
            "p95": r0(quantile(abs_errors, 0.95)),
        },
        "quantiles_signed_mw": {
            "p10": r0(quantile(errors, 0.10)),
            "p50": r0(quantile(errors, 0.50)),
            "p90": r0(p90_signed),
        },
        "shortfall": {
            "raw_positive_mwh": r0(bias_effect["raw_positive_mwh"]),
            "share_hours_short": r4(sum(error > 0 for error in errors) / len(errors)),
            "haircut_bias_mw": r0(bias_effect["haircut_mw"]),
            "extra_buy_bias_mwh": r0(bias_effect["extra_buy_mwh"]),
            "uncovered_after_bias_mwh": r0(bias_effect["uncovered_mwh"]),
            "haircut_p90_mw": r0(p90_effect["haircut_mw"]),
            "extra_buy_p90_mwh": r0(p90_effect["extra_buy_mwh"]),
            "uncovered_after_p90_mwh": r0(p90_effect["uncovered_mwh"]),
            "hours_covered_by_p90": r4(p90_effect["hours_covered"]),
        },
        "holdout": holdout,
        "by_day": by_day,
        "by_hour": by_hour,
        "by_vintage": by_vintage,
        "by_level": by_level,
        "histogram": histogram,
        "scatter": scatter,
        "worst_days": worst,
    }
    payload["narrative"] = _accuracy_narrative(payload)
    return payload


def _desk_narrative(delivery, auction, buffer_min, vintage, totals, previous, comparison, band, context) -> list[str]:
    if vintage is None:
        return [
            f"No WINDFOR file published at or before the deadline covers every hour of {_long_date(delivery)}."
        ]
    if buffer_min == 0:
        gate = f"the {auction.name} gate ({auction.gate_local} London)"
    else:
        gate = (
            f"the {auction.name} gate ({auction.gate_local} London, "
            f"brought forward {buffer_min} minutes so a bid can be rebuilt)"
        )
    lines = [
        (
            f"For delivery on {delivery.strftime('%A')} {_long_date(delivery)}, the last file at or before {gate} "
            f"was published at {vintage['publish_local']} London on {vintage['publish_date_label']}, "
            f"{_minute_phrase(vintage['minutes_before_deadline'])}."
        )
    ]
    if vintage["minutes_before_deadline"] == 0:
        lines.append(
            "That file is timestamped at the deadline itself. A desk that needs time to rebuild bids after the file lands should set a preparation buffer, which drops this run and uses the previous one."
        )
    if totals["forecast_mwh"] is not None:
        lines.append(
            (
                f"The file puts operational wind at {energy_phrase(totals['forecast_mwh'])} over the delivery day, "
                f"averaging {mw_phrase(totals['forecast_mean_mw'])}, from {mw_phrase(totals['forecast_min_mw'])} to {mw_phrase(totals['forecast_max_mw'])}."
            )
        )
    if previous and previous["delta_mwh"] is not None:
        delta = previous["delta_mwh"]
        if abs(delta) < 1:
            movement = "unchanged from"
        elif delta < 0:
            movement = f"{energy_phrase(abs(delta))} lower than"
        else:
            movement = f"{energy_phrase(delta)} higher than"
        lines.append(
            f"It is {movement} the previous available file ({previous['publish_local']} London)."
        )
    if comparison and comparison.get("same_file"):
        lines.append(f"{comparison['auction_name']} would have locked this same file.")
    elif comparison and comparison.get("forecast_mwh") is not None and totals["forecast_mwh"] is not None:
        delta = totals["forecast_mwh"] - comparison["forecast_mwh"]
        if comparison["auction_id"] == "epex_hourly" and auction.id == "n2ex":
            direction = "higher" if delta < 0 else "lower"
            lines.append(
                (
                    f"EPEX hourly closed at 09:20 and would have used the {comparison['publish_local']} file, "
                    f"which is {energy_phrase(abs(delta))} {direction} than the file still available for N2EX. "
                    "N2EX does not close until 09:50."
                )
            )
        else:
            direction = "higher" if delta < 0 else "lower"
            lines.append(
                (
                    f"{comparison['auction_name']} ({comparison['gate_local']} London) would have locked the "
                    f"{comparison['publish_local']} file, {energy_phrase(abs(delta))} {direction} than this one."
                )
            )
    if auction.id == "epex_half_hour":
        lines.append(
            "This auction clears half-hours. The wind file does not: both settlement periods in a clock hour carry the same forecast. The two half-hour outturns are shown so that unresolved shape stays visible."
        )
    if band is None:
        if context == "prior":
            lines.append(
                "There are fewer than 48 earlier hours in this January sample, so the desk does not draw an error band. Nothing in the month had outturned in time to size one."
            )
        else:
            lines.append("There is not enough scored history to draw an error band.")
    else:
        lines.append(
            (
                f"The shaded band uses this same gate rule on {band['basis']} "
                f"({band['hours_used']} hours, bias {mw_phrase(band['global_bias_mw'], signed=True)}). "
                "Positive bias means the file ran above the outturn. The band is a description of those misses, not a probabilistic forecast, and it was not known for the earliest days of the month."
            )
        )
        if totals.get("debiased_mwh") is not None and totals.get("forecast_mwh") is not None:
            lines.append(
                f"Removing that bias puts the day at {energy_phrase(totals['debiased_mwh'])}, against {energy_phrase(totals['forecast_mwh'])} in the raw file."
            )
    return lines


def _accuracy_narrative(payload: dict) -> list[str]:
    forecast = payload["forecast"]
    bias = forecast["bias_mw"]
    if bias > 25:
        bias_words = "The file ran high on average, so operational wind undershot it and an unadjusted buyer would have been short energy."
    elif bias < -25:
        bias_words = "The file ran low on average, so operational wind overshot it and an unadjusted buyer would have been long energy."
    else:
        bias_words = "Average bias was small beside the hour-to-hour scatter."
    lines = [
        (
            f"Across {payload['sample']['hours']} hours and {payload['sample']['days']} delivery days, "
            f"the gate-time file has MAE {mw_phrase(forecast['mae_mw'])}, RMSE {mw_phrase(forecast['rmse_mw'])} "
            f"and bias {mw_phrase(bias, signed=True)}. Error is forecast minus actual. {bias_words}"
        )
    ]
    persistence = payload.get("persistence")
    skill = payload.get("skill_vs_persistence")
    if persistence and skill is not None:
        if skill > 0.02:
            relation = "lower than"
            verdict = "The NESO file beat same-hour persistence on this month."
        elif skill < -0.02:
            relation = "higher than"
            verdict = "On this month the NESO file did not beat same-hour persistence."
        else:
            relation = "about the same as"
            verdict = "The NESO file and same-hour persistence were close on this month."
        hours_note = ""
        if payload["sample"]["persistence_hours"] != payload["sample"]["hours"]:
            hours_note = f" Skill uses the {payload['sample']['persistence_hours']} hours where the previous day’s outturn exists."
        lines.append(
            (
                f"Same-hour persistence, using the previous day’s FUELHH wind as the forecast, "
                f"has MAE {mw_phrase(persistence['mae_mw'])}. The gate-time file’s MAE is {relation} that. "
                f"Skill is {skill:.2f}, where zero matches persistence and one would mean no error. {verdict}{hours_note}"
            )
        )
    unresolved = payload.get("within_hour_unresolved_mw")
    span = payload.get("within_hour_span_mw")
    if unresolved is not None and span is not None:
        lines.append(
            (
                f"Inside each clock hour the two half-hours differed by {mw_phrase(span)} on average. "
                f"About {mw_phrase(unresolved)} of that is invisible to an hourly file. "
                f"Hourly MAE is {mw_phrase(forecast['mae_mw'])}, so the scored miss is mostly the hour being wrong rather than the shape inside it."
            )
        )
    holdout = payload.get("holdout")
    if holdout and holdout.get("test_hours"):
        lines.append(
            (
                f"A flat haircut fit only on {holdout['fit_label']} and applied to {holdout['test_label']}: "
                f"the fit window’s 90th percentile signed error was {mw_phrase(holdout['fit_p90_signed_mw'], signed=True)}. "
                f"On the held-out hours that haircut left {energy_phrase(holdout['test_uncovered_mwh'])} of shortfall energy uncovered, "
                f"against {energy_phrase(holdout['test_raw_positive_mwh'])} with no haircut, and covered {holdout['test_coverage_of_p90'] * 100:.1f}% of held-out hours. "
                "This is one split of a single month, scored on the same series it describes. It is not a forward test."
            )
        )
    rare = [row for row in payload.get("by_vintage", []) if row["n_days"] <= 2]
    if rare:
        clocks = ", ".join(row["slot_local"] + " London" for row in rare)
        lines.append(
            f"Publication clocks are taken from the files, not from a timetable. This extract has a rare clock at {clocks}, scored on its own rather than folded into the neighbouring run."
        )
    return lines


def _holdout(fit_pairs, test_pairs) -> dict:
    note = (
        "Quantiles are fit on 1–21 January and scored on 22–31 January. "
        "Both windows use the same gate rule. The haircut is not refit on the test days."
    )
    if not fit_pairs or not test_pairs:
        return {"fit_label": "1–21 January", "test_label": "22–31 January", "test_hours": 0, "note": note}
    fit_errors = [pair.error_mw for pair in fit_pairs]
    test_errors = [pair.error_mw for pair in test_pairs]
    fit_bias = sum(fit_errors) / len(fit_errors)
    fit_p90 = quantile(fit_errors, 0.90)
    effect = haircut_effect(test_errors, fit_p90)
    test_mae_raw = sum(abs(error) for error in test_errors) / len(test_errors)
    test_mae_debiased = sum(abs(error - fit_bias) for error in test_errors) / len(test_errors)
    return {
        "fit_label": "1–21 January",
        "test_label": "22–31 January",
        "fit_hours": len(fit_pairs),
        "test_hours": len(test_pairs),
        "fit_days": len({pair.delivery for pair in fit_pairs}),
        "test_days": len({pair.delivery for pair in test_pairs}),
        "fit_bias_mw": r0(fit_bias),
        "fit_p90_signed_mw": r0(fit_p90),
        "test_mae_raw_mw": r0(test_mae_raw),
        "test_mae_debiased_mw": r0(test_mae_debiased),
        "test_coverage_of_p90": r4(effect["hours_covered"]),
        "test_raw_positive_mwh": r0(effect["raw_positive_mwh"]),
        "test_uncovered_mwh": r0(effect["uncovered_mwh"]),
        "test_extra_buy_mwh": r0(effect["extra_buy_mwh"]),
        "note": note,
    }


def _by_day(pairs) -> list[dict]:
    grouped: dict[date, list] = {}
    for pair in pairs:
        grouped.setdefault(pair.delivery, []).append(pair)
    rows = []
    for delivery in sorted(grouped):
        chunk = grouped[delivery]
        errors = [pair.error_mw for pair in chunk]
        forecasts = [pair.forecast_mw for pair in chunk]
        actuals = [pair.actual_mw for pair in chunk]
        _date, clock = london_clock(chunk[0].publish)
        rows.append(
            {
                "delivery": delivery.isoformat(),
                "label": f"{delivery.day} {delivery.strftime('%b')}",
                "weekday": delivery.strftime("%a"),
                "hours": len(chunk),
                "forecast_mwh": r0(sum(forecasts)),
                "actual_mwh": r0(sum(actuals)),
                "error_mwh": r0(sum(errors)),
                "mae_mw": r0(sum(abs(error) for error in errors) / len(errors)),
                "bias_mw": r0(sum(errors) / len(errors)),
                "publish_local": clock,
            }
        )
    return rows


def _by_hour(pairs) -> list[dict]:
    grouped: dict[int, list] = {}
    for pair in pairs:
        grouped.setdefault(pair.hour_local, []).append(pair)
    rows = []
    for hour in range(24):
        chunk = grouped.get(hour, [])
        if not chunk:
            continue
        errors = [pair.error_mw for pair in chunk]
        rows.append(
            {
                "hour_local": hour,
                "label": f"{hour:02d}:00",
                "n": len(chunk),
                "mae_mw": r0(sum(abs(error) for error in errors) / len(errors)),
                "bias_mw": r0(sum(errors) / len(errors)),
                "mean_actual_mw": r0(sum(pair.actual_mw for pair in chunk) / len(chunk)),
            }
        )
    return rows


def _by_vintage(snapshot: Snapshot, auction: Auction, buffer_min: int) -> list[dict]:
    grouped: dict[str, list] = {}
    leads: dict[str, list] = {}
    for delivery in JANUARY_2026:
        midnight = datetime.combine(delivery, time(0, 0), tzinfo=LONDON)
        for publish, rows in slot_pairs_on_decision_day(
            snapshot.publishes, snapshot.forecasts, snapshot.actuals, delivery
        ):
            _day, clock = london_clock(publish)
            grouped.setdefault(clock, []).extend(rows)
            leads.setdefault(clock, []).append((midnight - parse_utc(publish)).total_seconds() / 3600)
    rows = []
    sample_day = date(2026, 1, 15)
    for clock in sorted(grouped):
        chunk = grouped[clock]
        errors = [pair.error_mw for pair in chunk]
        hour, minute = (int(part) for part in clock.split(":"))
        slot_time = datetime.combine(
            sample_day - timedelta(days=1),
            time(hour, minute),
            tzinfo=LONDON,
        )
        deadline = decision_deadline(sample_day, auction, buffer_min)
        rows.append(
            {
                "slot_local": clock,
                "before_gate": slot_time <= deadline,
                "n_days": len({pair.delivery for pair in chunk}),
                "n_hours": len(chunk),
                "mae_mw": r0(sum(abs(error) for error in errors) / len(errors)),
                "bias_mw": r0(sum(errors) / len(errors)),
                "lead_to_midnight_h": round(sum(leads[clock]) / len(leads[clock]), 1),
            }
        )
    return rows


def _by_level(pairs) -> list[dict]:
    model = error_model(pairs)
    if model is None:
        return []
    rows = []
    for band in model.bins:
        if band.hi_mw >= 40000:
            label = f"{band.lo_mw / 1000:.0f} GW and above"
        else:
            label = f"{band.lo_mw / 1000:.0f}–{band.hi_mw / 1000:.0f} GW"
        rows.append(
            {
                "label": label,
                "lo_mw": band.lo_mw,
                "hi_mw": band.hi_mw,
                "n": band.n,
                "mae_mw": r0(band.mae_mw),
                "bias_mw": r0(band.bias_mw),
                "p10_mw": r0(band.p10_mw),
                "p90_mw": r0(band.p90_mw),
            }
        )
    return rows


def _histogram(errors: list[float]) -> list[dict]:
    width = 200
    lowest = min(errors)
    highest = max(errors)
    start = math.floor(lowest / width) * width
    stop = math.ceil(highest / width) * width
    if stop <= start:
        stop = start + width
    if highest >= stop:
        stop += width
    rows = []
    cursor = start
    while cursor < stop:
        count = sum(1 for error in errors if cursor <= error < cursor + width)
        rows.append(
            {
                "from_mw": int(cursor),
                "to_mw": int(cursor + width),
                "label": f"{int(cursor)} to {int(cursor + width)}",
                "count": count,
            }
        )
        cursor += width
    return rows


def _vintages(snapshot: Snapshot, delivery: date, deadline: datetime, locked: str | None) -> list[dict]:
    locked_mwh = _day_mwh(snapshot, locked, delivery) if locked else None
    decision_day = delivery - timedelta(days=1)
    rows = []
    keys = hour_keys(delivery)
    for publish in snapshot.publishes:
        series = snapshot.forecasts[publish]
        if not covers(series, keys):
            continue
        local_date, clock = london_clock(publish)
        if local_date not in (decision_day, delivery):
            continue
        total = sum(series[key] for key in keys)
        available = parse_utc(publish) <= deadline
        rows.append(
            {
                "publish_utc": publish,
                "publish_local": clock,
                "publish_date": local_date.isoformat(),
                "day_offset_label": "Decision day" if local_date == decision_day else "Delivery day",
                "available": available,
                "locked": publish == locked,
                "forecast_mwh": r0(total),
                "delta_vs_locked_mwh": r0(total - locked_mwh) if locked_mwh is not None else None,
                "minutes_before_deadline": int(round((deadline - parse_utc(publish)).total_seconds() / 60)),
            }
        )
    return rows


def _previous_block(vintages: list[dict], locked: str | None) -> dict | None:
    if locked is None:
        return None
    earlier = [row for row in vintages if row["available"] and not row["locked"]]
    if not earlier:
        return None
    previous = earlier[-1]
    return {
        "publish_utc": previous["publish_utc"],
        "publish_local": previous["publish_local"],
        "forecast_mwh": previous["forecast_mwh"],
        "delta_mwh": r0((previous["delta_vs_locked_mwh"] or 0) * -1),
    }


def _comparison(snapshot, delivery, auction, buffer_min, locked_mwh, locked_publish) -> dict | None:
    other = AUCTIONS[COMPARE_WITH[auction.id]]
    deadline = decision_deadline(delivery, other, buffer_min)
    publish = select_publish(snapshot.publishes, snapshot.forecasts, delivery, deadline)
    total = _day_mwh(snapshot, publish, delivery) if publish else None
    clock = london_clock(publish)[1] if publish else None
    return {
        "auction_id": other.id,
        "auction_name": other.name,
        "gate_local": other.gate_local,
        "publish_utc": publish,
        "publish_local": clock,
        "forecast_mwh": r0(total),
        "delta_mwh": r0(locked_mwh - total) if locked_mwh is not None and total is not None else None,
        "same_file": publish is not None and publish == locked_publish,
    }


def _previous_publish(snapshot: Snapshot, delivery: date, deadline: datetime, locked: str | None) -> str | None:
    if locked is None:
        return None
    previous = None
    keys = hour_keys(delivery)
    deadline_iso = iso_z(deadline)
    for publish in snapshot.publishes:
        if publish > deadline_iso or publish >= locked:
            break
        if covers(snapshot.forecasts[publish], keys):
            previous = publish
    return previous


def _day_mwh(snapshot: Snapshot, publish: str | None, delivery: date) -> float | None:
    if publish is None:
        return None
    keys = hour_keys(delivery)
    series = snapshot.forecasts.get(publish)
    if series is None or not covers(series, keys):
        return None
    return float(sum(series[key] for key in keys))


def _hours(delivery: date):
    from backend.analysis import delivery_hour_starts

    return delivery_hour_starts(delivery)


def _settlement_period(moment: datetime) -> int:
    local = moment.astimezone(LONDON)
    return local.hour * 2 + local.minute // 30 + 1


def _long_date(day: date) -> str:
    return f"{day.day} {day.strftime('%B')}"


def _minute_phrase(minutes: int) -> str:
    if minutes == 0:
        return "at the deadline itself"
    if minutes == 1:
        return "1 minute before the deadline"
    if minutes > 1:
        return f"{minutes} minutes before the deadline"
    if minutes == -1:
        return "1 minute after the deadline"
    return f"{abs(minutes)} minutes after the deadline"


def _round_block(block: dict) -> dict:
    return {
        "n": block["n"],
        "mae_mw": r0(block["mae_mw"]),
        "rmse_mw": r0(block["rmse_mw"]),
        "bias_mw": r0(block["bias_mw"]),
        "wape": r4(block["wape"]),
        "mean_forecast_mw": r0(block["mean_forecast_mw"]),
        "mean_actual_mw": r0(block["mean_actual_mw"]),
        "energy_error_mwh": r0(block["energy_error_mwh"]),
    }


def r0(value) -> int | None:
    if value is None:
        return None
    return int(round(float(value)))


def r4(value) -> float | None:
    if value is None:
        return None
    return round(float(value), 4)


def energy_phrase(mwh: float | None) -> str:
    if mwh is None:
        return "an unknown energy"
    whole = int(round(float(mwh)))
    sign = "−" if whole < 0 else ""
    mag = abs(whole)
    if mag >= 1000:
        text = f"{mag / 1000:.1f}".rstrip("0").rstrip(".")
        return f"{sign}{text} GWh"
    return f"{sign}{mag:,} MWh"


def mw_phrase(mw: float | None, signed: bool = False) -> str:
    if mw is None:
        return "unknown MW"
    whole = int(round(float(mw)))
    sign = ""
    if whole < 0:
        sign = "−"
    elif signed and whole > 0:
        sign = "+"
    return f"{sign}{abs(whole):,} MW"
