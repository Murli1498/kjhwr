"""Gate selection, scoring, and the January snapshot."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend.analysis import (
    AUCTIONS,
    UTC,
    decision_deadline,
    decision_pairs,
    delivery_hour_starts,
    haircut_effect,
    hour_keys,
    iso_z,
    metric_block,
    quantile,
    select_publish,
    skill_score,
)
from backend.main import app
from backend.present import accuracy_payload, desk_payload
from backend.store import Snapshot, load_snapshot

JAN15 = date(2026, 1, 15)
N2EX = AUCTIONS["n2ex"]
EPEX = AUCTIONS["epex_hourly"]
EPEX_HH = AUCTIONS["epex_half_hour"]


def _publish(day: date, hour: int, minute: int) -> str:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _cover(delivery: date, generation: float) -> dict[str, float]:
    return {key: generation for key in hour_keys(delivery)}


def _actuals_for(delivery: date, sp1: float, sp2: float) -> dict[str, float]:
    rows = {}
    for start in delivery_hour_starts(delivery):
        rows[iso_z(start)] = sp1
        rows[iso_z(start + timedelta(minutes=30))] = sp2
    return rows


def _snapshot(actuals, forecasts) -> Snapshot:
    return Snapshot(actuals=actuals, forecasts=forecasts, meta={"fetched_at": "test"})


def test_january_gate_is_utc_and_july_gate_is_bst():
    winter = decision_deadline(JAN15, N2EX, 0)
    assert winter == datetime(2026, 1, 14, 9, 50, tzinfo=timezone.utc)
    summer = decision_deadline(date(2026, 7, 15), N2EX, 0)
    assert summer == datetime(2026, 7, 14, 8, 50, tzinfo=timezone.utc)


def test_buffer_brings_the_deadline_forward():
    deadline = decision_deadline(JAN15, N2EX, 20)
    assert deadline == datetime(2026, 1, 14, 9, 30, tzinfo=timezone.utc)


def test_clock_change_days_do_not_have_24_hours():
    assert len(delivery_hour_starts(JAN15)) == 24
    assert len(set(hour_keys(JAN15))) == 24
    assert len(delivery_hour_starts(date(2026, 3, 29))) == 23
    assert len(delivery_hour_starts(date(2026, 10, 25))) == 25


def test_latest_covering_file_respects_the_gate_and_the_buffer():
    early = _publish(date(2026, 1, 14), 7, 30)
    late = _publish(date(2026, 1, 14), 9, 30)
    forecasts = {early: _cover(JAN15, 1100), late: _cover(JAN15, 1000)}
    publishes = tuple(sorted(forecasts))
    n2ex_deadline = decision_deadline(JAN15, N2EX, 0)
    epex_deadline = decision_deadline(JAN15, EPEX, 0)
    buffered = decision_deadline(JAN15, N2EX, 30)
    assert select_publish(publishes, forecasts, JAN15, n2ex_deadline) == late
    assert select_publish(publishes, forecasts, JAN15, epex_deadline) == early
    assert select_publish(publishes, forecasts, JAN15, buffered) == early
    # A file timestamped exactly at the deadline is still usable.
    exact = decision_deadline(JAN15, N2EX, 20)
    assert select_publish(publishes, forecasts, JAN15, exact) == late


def test_incomplete_file_is_skipped():
    early = _publish(date(2026, 1, 14), 7, 30)
    late = _publish(date(2026, 1, 14), 9, 30)
    incomplete = _cover(JAN15, 1000)
    dropped = hour_keys(JAN15)[-1]
    del incomplete[dropped]
    forecasts = {early: _cover(JAN15, 1100), late: incomplete}
    chosen = select_publish(tuple(sorted(forecasts)), forecasts, JAN15, decision_deadline(JAN15, N2EX, 0))
    assert chosen == early


def test_hourly_actual_is_the_mean_of_the_two_settlement_periods():
    early = _publish(date(2026, 1, 14), 7, 30)
    late = _publish(date(2026, 1, 14), 9, 30)
    forecasts = {early: _cover(JAN15, 1100), late: _cover(JAN15, 1000)}
    actuals = _actuals_for(JAN15, 800, 1200)
    pairs = decision_pairs(tuple(sorted(forecasts)), forecasts, actuals, N2EX, 0, days=(JAN15,))
    assert len(pairs) == 24
    assert pairs[0].publish == late
    assert pairs[0].actual_mw == 1000
    assert pairs[0].error_mw == 0
    assert pairs[0].sp1_mw == 800 and pairs[0].sp2_mw == 1200


def test_positive_error_means_the_file_was_above_the_outturn():
    publish = _publish(date(2026, 1, 14), 9, 30)
    forecasts = {publish: _cover(JAN15, 1500)}
    actuals = _actuals_for(JAN15, 1000, 1000)
    pairs = decision_pairs(tuple(sorted(forecasts)), forecasts, actuals, N2EX, 0, days=(JAN15,))
    assert pairs[0].error_mw == 500


def test_metrics_and_skill_and_haircut():
    block = metric_block([10, 10], [8, 12])
    assert block["mae_mw"] == 2
    assert block["bias_mw"] == 0
    assert block["rmse_mw"] == 2
    assert block["energy_error_mwh"] == 0
    assert quantile(list(range(1, 11)), 0.9) == 9
    effect = haircut_effect([10, -5, 0], 10)
    assert effect["uncovered_mwh"] == 0
    assert effect["raw_positive_mwh"] == 10
    assert effect["extra_buy_mwh"] == 30
    assert skill_score(80, 100) == pytest.approx(0.2)
    # A negative haircut is not a recommendation to rely on more wind.
    assert haircut_effect([1, -8], -4)["haircut_mw"] == 0


def test_missing_settlement_period_drops_the_hour_only():
    publish = _publish(date(2026, 1, 14), 9, 30)
    forecasts = {publish: _cover(JAN15, 1000)}
    actuals = _actuals_for(JAN15, 900, 900)
    first_hour = delivery_hour_starts(JAN15)[0]
    del actuals[iso_z(first_hour + timedelta(minutes=30))]
    pairs = decision_pairs(tuple(sorted(forecasts)), forecasts, actuals, N2EX, 0, days=(JAN15,))
    assert len(pairs) == 23


def test_desk_revision_uses_the_previous_available_file():
    early = _publish(date(2026, 1, 14), 7, 30)
    late = _publish(date(2026, 1, 14), 9, 30)
    forecasts = {early: _cover(JAN15, 1100), late: _cover(JAN15, 1000)}
    actuals = _actuals_for(JAN15, 1000, 1000)
    # Previous day so a prior-context band is not required for this assertion.
    snapshot = _snapshot(actuals, forecasts)
    payload = desk_payload(snapshot, JAN15, N2EX, 0, "prior")
    assert payload["vintage"]["publish_local"] == "09:30"
    assert payload["previous"]["publish_local"] == "07:30"
    assert payload["previous"]["delta_mwh"] == 1000 * 24 - 1100 * 24
    assert payload["comparison"]["auction_id"] == "epex_hourly"
    assert payload["comparison"]["publish_local"] == "07:30"
    assert payload["hours"][0]["sp_start"] == 1
    assert payload["hours"][0]["sp_end"] == 2
    text = " ".join(payload["narrative"])
    assert "09:30" in text
    assert "09:50" in text
    assert "lower" in text


def test_api_rejects_a_delivery_day_outside_the_pilot():
    client = TestClient(app)
    response = client.get("/api/desk", params={"delivery": "2026-02-01"})
    assert response.status_code == 400
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["ok"] is True


def test_january_snapshot_locks_the_expected_morning_files():
    snapshot = load_snapshot()
    n2ex = decision_pairs(snapshot.publishes, snapshot.forecasts, snapshot.actuals, N2EX, 0)
    epex = decision_pairs(snapshot.publishes, snapshot.forecasts, snapshot.actuals, EPEX, 0)
    half = decision_pairs(snapshot.publishes, snapshot.forecasts, snapshot.actuals, EPEX_HH, 0)
    assert len(n2ex) == 31 * 24
    assert len({pair.delivery for pair in n2ex}) == 31
    assert {pair.publish[11:16] for pair in n2ex} == {"09:30"}
    assert {pair.publish[11:16] for pair in epex} == {"07:30"}
    assert {pair.publish[11:16] for pair in half} == {"15:30"}

    desk = desk_payload(snapshot, JAN15, N2EX, 0, "retrospective")
    assert desk["vintage"]["minutes_before_deadline"] == 20
    assert desk["totals"]["paired_hours"] == 24
    assert desk["totals"]["forecast_hours"] == 24
    # The 15:30 file is timestamped on the half-hour gate. One minute of buffer drops it.
    buffered = desk_payload(snapshot, JAN15, EPEX_HH, 1, "prior")
    assert buffered["vintage"]["publish_utc"].endswith("T11:30:00Z")

    scored = accuracy_payload(snapshot, N2EX, 0)
    assert scored["sample"]["hours"] == 744
    assert scored["sample"]["days"] == 31
    assert scored["sample"]["missing_days"] == []
    assert scored["sample"]["missing_hours"] == 0
    assert scored["sample"]["persistence_hours"] == 744
    assert scored["forecast"]["mae_mw"] > 0
    assert scored["skill_vs_persistence"] is not None
    assert scored["correlation"] > 0.5
    assert scored["holdout"]["fit_hours"] == 21 * 24
    assert scored["holdout"]["test_hours"] == 10 * 24
    # In-sample, a 90th percentile haircut covers at least 90% of the hours it was fit on.
    assert scored["shortfall"]["hours_covered_by_p90"] >= 0.9
    clocks = {row["slot_local"]: row["n_days"] for row in scored["by_vintage"]}
    assert clocks["09:30"] == 31
    assert clocks["12:25"] == 1
    csv_response = TestClient(app).get("/api/desk.csv", params={"delivery": "2026-01-15", "auction": "n2ex"})
    assert csv_response.status_code == 200
    assert csv_response.text.splitlines()[0].startswith("delivery,hour_local")
    assert len(csv_response.text.splitlines()) == 25
