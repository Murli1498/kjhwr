"""Load the Elexon snapshot. The application never calls BMRS at request time."""

from __future__ import annotations

import json
import os
from pathlib import Path

from backend.analysis import iso_z, parse_utc


def default_data_path() -> Path:
    override = os.environ.get("DATA_PATH")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[1] / "data" / "elexon_january_2026.json"


class Snapshot:
    def __init__(self, actuals: dict[str, float], forecasts: dict[str, dict[str, float]], meta: dict):
        self.actuals = actuals
        self.forecasts = forecasts
        self.meta = meta
        self.publishes = tuple(sorted(forecasts))

    @property
    def forecast_rows(self) -> int:
        return sum(len(series) for series in self.forecasts.values())


def _canonical(value: str) -> str:
    return iso_z(parse_utc(value))


def load_snapshot(path: Path | None = None) -> Snapshot:
    location = path or default_data_path()
    if not location.exists():
        raise FileNotFoundError(
            f"Snapshot not found at {location}. Run: python scripts/fetch_elexon.py"
        )
    payload = json.loads(location.read_text(encoding="utf-8"))
    actuals: dict[str, float] = {}
    for start, generation in payload["actuals"]:
        actuals[_canonical(start)] = float(generation)
    forecasts: dict[str, dict[str, float]] = {}
    for publish, start, generation in payload["forecasts"]:
        forecasts.setdefault(_canonical(publish), {})[_canonical(start)] = float(generation)
    return Snapshot(actuals=actuals, forecasts=forecasts, meta=payload.get("meta", {}))
