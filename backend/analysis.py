"""Gate selection, alignment, and error metrics.

Error is forecast minus actual, in MW, on the clock hour. A positive error
means operational wind came in below the file (an undershoot). A buyer who
subtracted that file from demand would be short by the same number of MWh
and would have to buy the difference later.

WINDFOR is hourly. FUELHH is the average MW of each half-hour. The hourly
actual is the mean of the two settlement periods inside the clock hour, which
is also the energy-weighted outturn for that hour.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

LONDON = ZoneInfo("Europe/London")
UTC = timezone.utc

JANUARY_2026 = tuple(date(2026, 1, day) for day in range(1, 32))
FIT_UNTIL = date(2026, 1, 21)
TEST_FROM = date(2026, 1, 22)
LEVEL_EDGES = (0, 2000, 4000, 6000, 8000, 10000, 12000, 14000, 16000, 40000)
MIN_BIN = 24


@dataclass(frozen=True)
class Auction:
    id: str
    name: str
    gate_hour: int
    gate_minute: int
    product: str
    detail: str

    @property
    def gate_local(self) -> str:
        return f"{self.gate_hour:02d}:{self.gate_minute:02d}"


AUCTIONS: dict[str, Auction] = {
    "n2ex": Auction(
        id="n2ex",
        name="N2EX day-ahead",
        gate_hour=9,
        gate_minute=50,
        product="Hourly",
        detail=(
            "Nord Pool GB day-ahead auction. Order book closes at 09:50 London. "
            "Results are published by 10:00 London."
        ),
    ),
    "epex_hourly": Auction(
        id="epex_hourly",
        name="EPEX day-ahead hourly",
        gate_hour=9,
        gate_minute=20,
        product="Hourly",
        detail=(
            "EPEX SPOT GB 60-minute day-ahead auction. Order book closes at 09:20 London. "
            "Results are published from 09:30 London."
        ),
    ),
    "epex_half_hour": Auction(
        id="epex_half_hour",
        name="EPEX day-ahead half-hourly",
        gate_hour=15,
        gate_minute=30,
        product="Half-hourly",
        detail=(
            "EPEX SPOT GB 30-minute day-ahead auction. Order book closes at 15:30 London. "
            "Results are published from 15:45 London. WINDFOR is still an hourly file, "
            "so this auction can refresh the level but not the shape inside the hour."
        ),
    ),
}

COMPARE_WITH = {
    "n2ex": "epex_hourly",
    "epex_hourly": "n2ex",
    "epex_half_hour": "n2ex",
}


def parse_utc(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def iso_z(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def delivery_hour_starts(delivery: date) -> list[datetime]:
    """UTC start of each clock hour in the London delivery day.

    Stepping is done in UTC. Adding a timedelta to a London datetime follows
    the wall clock and, on the spring-forward morning, lands twice on the same
    instant. A normal day has 24 hours, the last Sunday in March has 23, and
    the last Sunday in October has 25. January 2026 has 24.
    """
    start = datetime.combine(delivery, time(0, 0), tzinfo=LONDON).astimezone(UTC)
    end = datetime.combine(delivery + timedelta(days=1), time(0, 0), tzinfo=LONDON).astimezone(UTC)
    hours: list[datetime] = []
    cursor = start.replace(microsecond=0)
    while cursor < end:
        hours.append(cursor)
        cursor += timedelta(hours=1)
    return hours


def hour_keys(delivery: date) -> tuple[str, ...]:
    return tuple(iso_z(hour) for hour in delivery_hour_starts(delivery))


def decision_deadline(delivery: date, auction: Auction, buffer_min: int) -> datetime:
    """London gate on D-1, brought forward by the preparation buffer.

    A file is usable when its publish time is at or before this instant.
    """
    gate = datetime.combine(
        delivery - timedelta(days=1),
        time(auction.gate_hour, auction.gate_minute),
        tzinfo=LONDON,
    )
    return gate - timedelta(minutes=buffer_min)


def london_clock(value: str) -> tuple[date, str]:
    moment = parse_utc(value).astimezone(LONDON)
    return moment.date(), moment.strftime("%H:%M")


def quantile(values: list[float], probability: float) -> float:
    """Nearest-rank quantile. At least `probability` of the sample is at or below it."""
    if not values:
        raise ValueError("quantile of an empty sample")
    ordered = sorted(values)
    if probability <= 0:
        return ordered[0]
    if probability >= 1:
        return ordered[-1]
    rank = math.ceil(probability * len(ordered)) - 1
    rank = min(max(rank, 0), len(ordered) - 1)
    return ordered[rank]


def pearson(xs: list[float], ys: list[float]) -> float | None:
    count = len(xs)
    if count < 2 or count != len(ys):
        return None
    mean_x = sum(xs) / count
    mean_y = sum(ys) / count
    covariance = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    scale_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    scale_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    if scale_x == 0 or scale_y == 0:
        return None
    return covariance / (scale_x * scale_y)


@dataclass(frozen=True)
class Pair:
    delivery: date
    start: datetime
    hour_local: int
    publish: str
    forecast_mw: float
    sp1_mw: float
    sp2_mw: float

    @property
    def actual_mw(self) -> float:
        return (self.sp1_mw + self.sp2_mw) / 2

    @property
    def error_mw(self) -> float:
        return self.forecast_mw - self.actual_mw


@dataclass(frozen=True)
class LevelBin:
    lo_mw: float
    hi_mw: float
    n: int
    bias_mw: float
    p10_mw: float
    p90_mw: float
    mae_mw: float


@dataclass(frozen=True)
class ErrorModel:
    n: int
    days: int
    bias_mw: float
    p10_mw: float
    p90_mw: float
    bins: tuple[LevelBin, ...]

    def apply(self, forecast_mw: float) -> tuple[float, float, float]:
        """Return debiased MW, band low, band high for a forecast level.

        The band is the 10th to 90th percentile of historical (forecast - actual),
        mapped back onto the MW the outturn occupied.
        """
        bias, low_error, high_error = self.bias_mw, self.p10_mw, self.p90_mw
        for band in self.bins:
            if band.n >= MIN_BIN and band.lo_mw <= forecast_mw < band.hi_mw:
                bias, low_error, high_error = band.bias_mw, band.p10_mw, band.p90_mw
                break
        return forecast_mw - bias, forecast_mw - high_error, forecast_mw - low_error


def covers(series: dict[str, float], keys: tuple[str, ...]) -> bool:
    return all(key in series for key in keys)


def select_publish(
    publishes: tuple[str, ...],
    forecasts: dict[str, dict[str, float]],
    delivery: date,
    deadline: datetime,
) -> str | None:
    """Latest publication at or before the deadline that contains every delivery hour."""
    keys = hour_keys(delivery)
    deadline_iso = iso_z(deadline)
    chosen = None
    for publish in publishes:
        if publish > deadline_iso:
            break
        if covers(forecasts[publish], keys):
            chosen = publish
    return chosen


def actual_hour(actuals: dict[str, float], hour_start: datetime) -> tuple[float, float] | None:
    first = actuals.get(iso_z(hour_start))
    second = actuals.get(iso_z(hour_start + timedelta(minutes=30)))
    if first is None or second is None:
        return None
    return first, second


def decision_pairs(
    publishes: tuple[str, ...],
    forecasts: dict[str, dict[str, float]],
    actuals: dict[str, float],
    auction: Auction,
    buffer_min: int,
    days: tuple[date, ...] = JANUARY_2026,
) -> list[Pair]:
    pairs: list[Pair] = []
    for delivery in days:
        deadline = decision_deadline(delivery, auction, buffer_min)
        publish = select_publish(publishes, forecasts, delivery, deadline)
        if publish is None:
            continue
        series = forecasts[publish]
        for hour_start in delivery_hour_starts(delivery):
            observed = actual_hour(actuals, hour_start)
            if observed is None:
                continue
            key = iso_z(hour_start)
            if key not in series:
                continue
            local_hour = hour_start.astimezone(LONDON).hour
            pairs.append(
                Pair(
                    delivery=delivery,
                    start=hour_start,
                    hour_local=local_hour,
                    publish=publish,
                    forecast_mw=series[key],
                    sp1_mw=observed[0],
                    sp2_mw=observed[1],
                )
            )
    return pairs


def slot_pairs_on_decision_day(
    publishes: tuple[str, ...],
    forecasts: dict[str, dict[str, float]],
    actuals: dict[str, float],
    delivery: date,
) -> list[tuple[str, list[Pair]]]:
    """Every full-day publication issued on the London decision day, oldest first."""
    decision_day = delivery - timedelta(days=1)
    found: list[tuple[str, list[Pair]]] = []
    for publish in publishes:
        local_date, _clock = london_clock(publish)
        if local_date != decision_day:
            continue
        if not covers(forecasts[publish], hour_keys(delivery)):
            continue
        rows: list[Pair] = []
        series = forecasts[publish]
        for hour_start in delivery_hour_starts(delivery):
            observed = actual_hour(actuals, hour_start)
            if observed is None:
                continue
            rows.append(
                Pair(
                    delivery=delivery,
                    start=hour_start,
                    hour_local=hour_start.astimezone(LONDON).hour,
                    publish=publish,
                    forecast_mw=series[iso_z(hour_start)],
                    sp1_mw=observed[0],
                    sp2_mw=observed[1],
                )
            )
        found.append((publish, rows))
    return found


def metric_block(forecasts: list[float], actuals: list[float]) -> dict:
    count = len(forecasts)
    if count == 0 or count != len(actuals):
        raise ValueError("forecasts and actuals must be the same non-empty length")
    errors = [forecast - actual for forecast, actual in zip(forecasts, actuals)]
    absolute = [abs(error) for error in errors]
    sum_actual = sum(actuals)
    return {
        "n": count,
        "mae_mw": sum(absolute) / count,
        "rmse_mw": math.sqrt(sum(error * error for error in errors) / count),
        "bias_mw": sum(errors) / count,
        "wape": (sum(absolute) / sum_actual) if sum_actual else None,
        "mean_forecast_mw": sum(forecasts) / count,
        "mean_actual_mw": sum_actual / count,
        "energy_error_mwh": sum(errors),
    }


def error_model(pairs: list[Pair]) -> ErrorModel | None:
    if not pairs:
        return None
    errors = [pair.error_mw for pair in pairs]
    bins: list[LevelBin] = []
    for lo, hi in zip(LEVEL_EDGES, LEVEL_EDGES[1:]):
        group = [pair for pair in pairs if lo <= pair.forecast_mw < hi]
        if not group:
            continue
        group_errors = [pair.error_mw for pair in group]
        bins.append(
            LevelBin(
                lo_mw=lo,
                hi_mw=hi,
                n=len(group),
                bias_mw=sum(group_errors) / len(group),
                p10_mw=quantile(group_errors, 0.10),
                p90_mw=quantile(group_errors, 0.90),
                mae_mw=sum(abs(error) for error in group_errors) / len(group),
            )
        )
    return ErrorModel(
        n=len(pairs),
        days=len({pair.delivery for pair in pairs}),
        bias_mw=sum(errors) / len(errors),
        p10_mw=quantile(errors, 0.10),
        p90_mw=quantile(errors, 0.90),
        bins=tuple(bins),
    )


def haircut_effect(errors: list[float], haircut_mw: float) -> dict:
    """Buy `haircut_mw` extra every hour. Report the shortfall energy that remains.

    Shortfall energy is the sum of positive (forecast - actual) after the haircut,
    in MWh. Each scored hour is one hour long.
    """
    haircut = max(0.0, haircut_mw)
    raw = sum(max(0.0, error) for error in errors)
    uncovered = sum(max(0.0, error - haircut) for error in errors)
    return {
        "haircut_mw": haircut,
        "extra_buy_mwh": haircut * len(errors),
        "raw_positive_mwh": raw,
        "uncovered_mwh": uncovered,
        "hours_covered": sum(1 for error in errors if error <= haircut) / len(errors) if errors else None,
    }


def persistence_forecasts(
    actuals: dict[str, float],
    pairs: list[Pair],
) -> tuple[list[float], list[float], list[float]]:
    """Yesterday's same-hour outturn, on the hours where it exists.

    Returns persistence forecast, the decision-file forecast, and the actual,
    so the skill score uses one common set of hours.
    """
    persisted: list[float] = []
    filed: list[float] = []
    observed: list[float] = []
    for pair in pairs:
        yesterday = actual_hour(actuals, pair.start - timedelta(days=1))
        if yesterday is None:
            continue
        persisted.append((yesterday[0] + yesterday[1]) / 2)
        filed.append(pair.forecast_mw)
        observed.append(pair.actual_mw)
    return persisted, filed, observed


def skill_score(forecast_mae: float, baseline_mae: float) -> float | None:
    if baseline_mae == 0:
        return None
    return 1 - forecast_mae / baseline_mae
