#!/usr/bin/env python3
"""Download the January 2026 Elexon snapshot used by Windgate.

Actuals: FUELHH, fuelType WIND, half-hourly average MW.
Forecasts: WINDFOR publications. The stream is filtered by publish time,
so the window starts on 30 December 2025 (decision morning for 1 January,
plus one extra day of actuals for the persistence benchmark).

The running application reads data/elexon_january_2026.json and does not
call Elexon on each request.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "elexon_january_2026.json"
BASE = "https://data.elexon.co.uk/bmrs/api/v1/datasets"
HEADERS = {
    "Accept": "application/json",
    "User-Agent": "WindgatePilot/1.0 (january-2026 day-ahead wind pilot)",
}


def get_json(url: str):
    last_error = "unknown"
    for attempt in range(4):
        request = urllib.request.Request(url, headers=HEADERS)
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:400]
            last_error = f"HTTP {exc.code} {body}"
            if exc.code in (429, 500, 502, 503) and attempt < 3:
                time.sleep(2 ** attempt)
                continue
            raise SystemExit(f"{url}\n{last_error}") from exc
        except urllib.error.URLError as exc:
            last_error = str(exc)
            if attempt < 3:
                time.sleep(2 ** attempt)
                continue
            raise SystemExit(f"{url}\n{last_error}") from exc
    raise SystemExit(last_error)


def as_rows(payload) -> list:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        return payload["data"]
    raise SystemExit(f"Unexpected payload: {str(payload)[:240]}")


def num(value):
    number = float(value)
    if number.is_integer():
        return int(number)
    return round(number, 3)


def canonical(value: str) -> str:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_actuals() -> list:
    query = urllib.parse.urlencode(
        {
            "settlementDateFrom": "2025-12-30",
            "settlementDateTo": "2026-01-31",
            "fuelType": "WIND",
        }
    )
    rows = as_rows(get_json(f"{BASE}/FUELHH/stream?{query}"))
    actuals = {}
    for row in rows:
        if row.get("fuelType") != "WIND":
            continue
        actuals[canonical(row["startTime"])] = num(row["generation"])
    print(f"FUELHH wind rows: {len(actuals)}")
    return [[start, mw] for start, mw in sorted(actuals.items())]


def fetch_forecasts() -> list:
    start = datetime(2025, 12, 30, tzinfo=timezone.utc)
    end = datetime(2026, 2, 1, tzinfo=timezone.utc)
    forecasts = {}
    cursor = start
    while cursor < end:
        nxt = min(cursor + timedelta(days=3), end)
        query = urllib.parse.urlencode(
            {
                "publishDateTimeFrom": cursor.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "publishDateTimeTo": nxt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        )
        rows = as_rows(get_json(f"{BASE}/WINDFOR/stream?{query}"))
        for row in rows:
            key = (canonical(row["publishTime"]), canonical(row["startTime"]))
            forecasts[key] = num(row["generation"])
        print(f"WINDFOR {cursor.date()} -> {nxt.date()}: {len(rows)} rows, {len(forecasts)} unique")
        cursor = nxt
        time.sleep(0.35)
    return [[pub, start_time, mw] for (pub, start_time), mw in sorted(forecasts.items())]


def summarise(actuals: list, forecasts: list) -> None:
    pubs = {}
    for pub, _start, _mw in forecasts:
        pubs.setdefault(pub[:10], 0)
        pubs[pub[:10]] += 1
    print(f"publications by day: {min(pubs)} .. {max(pubs)} ({len(pubs)} days)")
    hours = {}
    for pub, _start, _mw in forecasts:
        hours.setdefault(pub, set()).add(_start)
    lengths = sorted({len(v) for v in hours.values()})
    print(f"points per publication: {lengths}")
    minutes = sorted({start[14:16] for _pub, start, _mw in forecasts})
    print(f"forecast start minutes: {minutes}")
    actual_minutes = sorted({start[14:16] for start, _mw in actuals})
    print(f"actual start minutes: {actual_minutes}")
    january = [date(2026, 1, day) for day in range(1, 32)]
    missing = []
    for day in january:
        needed = [
            datetime(day.year, day.month, day.day, hour, tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            for hour in range(24)
        ]
        deadline = datetime(day.year, day.month, day.day, 9, 50, tzinfo=timezone.utc) - timedelta(days=1)
        deadline_s = deadline.strftime("%Y-%m-%dT%H:%M:%SZ")
        found = False
        for pub, starts in hours.items():
            if pub <= deadline_s and all(hour in starts for hour in needed):
                found = True
                break
        if not found:
            missing.append(day.isoformat())
    print(f"January days without a full file at or before 09:50 UTC on D-1: {missing or 'none'}")


def main() -> None:
    actuals = fetch_actuals()
    forecasts = fetch_forecasts()
    summarise(actuals, forecasts)
    payload = {
        "meta": {
            "source": "Elexon Insights Solution",
            "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "endpoints": [
                f"{BASE}/FUELHH/stream",
                f"{BASE}/WINDFOR/stream",
            ],
            "actual_settlement_from": "2025-12-30",
            "actual_settlement_to": "2026-01-31",
            "forecast_publish_from": "2025-12-30T00:00:00Z",
            "forecast_publish_to": "2026-02-01T00:00:00Z",
            "fuel_type": "WIND",
            "notes": [
                "FUELHH generation is the half-hourly average MW for transmission-connected wind with operational metering.",
                "30 and 31 December 2025 actuals are included so 1 January has a same-hour persistence baseline.",
                "WINDFOR rows are hourly. Publications are whatever Elexon returned for the publish-time window.",
            ],
        },
        "actuals": actuals,
        "forecasts": forecasts,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUT.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    temporary.replace(OUT)
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
