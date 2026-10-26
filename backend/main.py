"""HTTP API and, when the frontend has been built, the static desk."""

from __future__ import annotations

import csv
import io
import os
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from backend.analysis import AUCTIONS
from backend.present import accuracy_payload, calendar_payload, desk_payload, meta_payload
from backend.store import Snapshot, load_snapshot

STATIC_DIR = Path(os.environ.get("STATIC_DIR", Path(__file__).resolve().parents[1] / "frontend" / "dist"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.snapshot = load_snapshot()
    yield


app = FastAPI(
    title="Windgate",
    summary="Day-ahead operational wind for a GB buyer, January 2026.",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _snapshot(request: Request) -> Snapshot:
    snapshot = getattr(request.app.state, "snapshot", None)
    if snapshot is None:
        snapshot = load_snapshot()
        request.app.state.snapshot = snapshot
    return snapshot


def _delivery(value: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="delivery must be YYYY-MM-DD") from exc
    if parsed.year != 2026 or parsed.month != 1:
        raise HTTPException(status_code=400, detail="This pilot only covers delivery days in January 2026.")
    return parsed


def _auction(value: str):
    try:
        return AUCTIONS[value]
    except KeyError as exc:
        raise HTTPException(
            status_code=400,
            detail="auction must be n2ex, epex_hourly, or epex_half_hour",
        ) from exc


def _buffer(value: int) -> int:
    if value < 0 or value > 360:
        raise HTTPException(status_code=400, detail="buffer_min must be between 0 and 360.")
    return value


def _context(value: str) -> str:
    if value not in ("prior", "retrospective"):
        raise HTTPException(status_code=400, detail="context must be prior or retrospective.")
    return value


@app.get("/api/health")
def health(request: Request):
    snapshot = _snapshot(request)
    return {
        "ok": True,
        "actuals": len(snapshot.actuals),
        "publications": len(snapshot.publishes),
        "fetched_at": snapshot.meta.get("fetched_at"),
    }


@app.get("/api/meta")
def meta(request: Request):
    return meta_payload(_snapshot(request))


@app.get("/api/calendar")
def calendar(
    request: Request,
    auction: str = "n2ex",
    buffer_min: int = 0,
):
    return calendar_payload(_snapshot(request), _auction(auction), _buffer(buffer_min))


@app.get("/api/desk")
def desk(
    request: Request,
    delivery: str,
    auction: str = "n2ex",
    buffer_min: int = 0,
    context: str = "prior",
):
    return desk_payload(
        _snapshot(request),
        _delivery(delivery),
        _auction(auction),
        _buffer(buffer_min),
        _context(context),
    )


@app.get("/api/desk.csv")
def desk_csv(
    request: Request,
    delivery: str,
    auction: str = "n2ex",
    buffer_min: int = 0,
    context: str = "prior",
):
    payload = desk_payload(
        _snapshot(request),
        _delivery(delivery),
        _auction(auction),
        _buffer(buffer_min),
        _context(context),
    )
    if payload["vintage"] is None:
        raise HTTPException(status_code=404, detail="No locked wind file for that gate.")
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "delivery",
            "hour_local",
            "start_utc",
            "settlement_period_start",
            "settlement_period_end",
            "forecast_mw",
            "debiased_mw",
            "band_low_mw",
            "band_high_mw",
            "actual_sp1_mw",
            "actual_sp2_mw",
            "actual_hour_mw",
            "error_mw",
            "publish_utc",
        ]
    )
    for hour in payload["hours"]:
        writer.writerow(
            [
                payload["delivery"],
                hour["label"],
                hour["start_utc"],
                hour["sp_start"],
                hour["sp_end"],
                hour["forecast_mw"],
                hour["debiased_mw"],
                hour["band_low_mw"],
                hour["band_high_mw"],
                hour["actual_sp1_mw"],
                hour["actual_sp2_mw"],
                hour["actual_mw"],
                hour["error_mw"],
                payload["vintage"]["publish_utc"],
            ]
        )
    filename = f"windgate-{payload['delivery']}-{payload['auction']['id']}.csv"
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/accuracy")
def accuracy(
    request: Request,
    auction: str = "n2ex",
    buffer_min: int = 0,
):
    return accuracy_payload(_snapshot(request), _auction(auction), _buffer(buffer_min))


@app.get("/")
def index():
    page = STATIC_DIR / "index.html"
    if not page.exists():
        return {
            "service": "windgate",
            "ui": "Frontend is not built. Run npm run build in frontend/, or use the API at /docs.",
            "docs": "/docs",
        }
    return FileResponse(page)


@app.get("/favicon.svg")
def favicon():
    icon = STATIC_DIR / "favicon.svg"
    if not icon.exists():
        raise HTTPException(status_code=404, detail="No favicon has been built.")
    return FileResponse(icon, media_type="image/svg+xml")


assets = STATIC_DIR / "assets"
if assets.exists():
    app.mount("/assets", StaticFiles(directory=assets), name="assets")
