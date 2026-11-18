"""
IoT data ingestion API routes.

POST /api/v1/iot/ingest           — Ingest a single or batch of sensor readings
GET  /api/v1/iot/{asset_id}/latest — Latest reading per metric for an asset
GET  /api/v1/iot/{asset_id}/timeseries — Historical readings for a metric
GET  /api/v1/iot/{asset_id}/daily  — Daily aggregates for a metric
GET  /api/v1/iot/inverter/{vendor}/current — Simulated inverter reading
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.digital_twin.iot.timeseries_db import (
    init_timeseries_schema,
    write_measurement,
    write_measurements_bulk,
    read_timeseries,
    get_latest,
    get_daily_aggregates,
)
from app.digital_twin.iot.inverter_apis import get_adapter, list_supported_vendors

router = APIRouter(prefix="/api/v1/iot", tags=["IoT"])

# Ensure DB schema exists on first import
_schema_ready = False


def _ensure_schema() -> None:
    global _schema_ready
    if not _schema_ready:
        init_timeseries_schema()
        _schema_ready = True


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class MeasurementIn(BaseModel):
    asset_id: str = Field(..., description="Unique asset identifier")
    metric: str = Field(
        ...,
        description=(
            "Metric name: pv/power, pv/irradiance, bess/soc, bess/soh, "
            "meter/import, meter/export, weather/temp"
        ),
    )
    value: float
    timestamp: Optional[datetime] = Field(
        None, description="UTC timestamp; defaults to server time"
    )


class BatchIngestIn(BaseModel):
    readings: list[MeasurementIn] = Field(..., min_length=1, max_length=1000)


class LatestReadingOut(BaseModel):
    asset_id: str
    metric: str
    value: Optional[float]
    timestamp: Optional[str]


class TimeseriesOut(BaseModel):
    asset_id: str
    metric: str
    start: str
    end: str
    count: int
    data: list[dict]   # [{time, value}, ...]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/ingest", summary="Ingest sensor readings")
def ingest(body: BatchIngestIn):
    """
    Accept one or more sensor readings and persist them to TimescaleDB.
    Use this endpoint to push data from inverters, meters, or weather sensors.
    """
    _ensure_schema()
    rows = [
        {
            "asset_id": r.asset_id,
            "metric": r.metric,
            "value": r.value,
            "time": r.timestamp or datetime.now(timezone.utc),
        }
        for r in body.readings
    ]
    write_measurements_bulk(rows)
    return {"status": "ok", "ingested": len(rows)}


@router.post("/ingest/single", summary="Ingest a single sensor reading")
def ingest_single(body: MeasurementIn):
    _ensure_schema()
    write_measurement(
        body.asset_id,
        body.metric,
        body.value,
        body.timestamp or datetime.now(timezone.utc),
    )
    return {"status": "ok"}


@router.get("/{asset_id}/latest", response_model=list[LatestReadingOut])
def get_latest_readings(asset_id: str):
    """Return the most recent reading for every standard metric of an asset."""
    _ensure_schema()
    metrics = [
        "pv/power", "pv/irradiance",
        "bess/soc", "bess/soh",
        "meter/import", "meter/export",
        "weather/temp",
    ]
    results = []
    for metric in metrics:
        value, ts = get_latest(asset_id, metric)
        results.append(
            LatestReadingOut(
                asset_id=asset_id,
                metric=metric,
                value=value,
                timestamp=ts.isoformat() if ts else None,
            )
        )
    return results


@router.get("/{asset_id}/timeseries", response_model=TimeseriesOut)
def get_timeseries(
    asset_id: str,
    metric: str = Query(..., description="Metric name, e.g. pv/power"),
    start: datetime = Query(..., description="Start time (ISO-8601 UTC)"),
    end: datetime = Query(..., description="End time (ISO-8601 UTC)"),
):
    """Return raw time-series data for a specific asset and metric."""
    _ensure_schema()
    if end <= start:
        raise HTTPException(status_code=400, detail="end must be after start")

    df = read_timeseries(asset_id, metric, start, end)
    data = [
        {"time": idx.isoformat(), "value": float(row["value"])}
        for idx, row in df.iterrows()
    ]
    return TimeseriesOut(
        asset_id=asset_id,
        metric=metric,
        start=start.isoformat(),
        end=end.isoformat(),
        count=len(data),
        data=data,
    )


@router.get("/{asset_id}/daily")
def get_daily(
    asset_id: str,
    metric: str = Query(..., description="Metric name, e.g. meter/import"),
    start: datetime = Query(...),
    end: datetime = Query(...),
    agg: str = Query("sum", description="Aggregation: 'sum' or 'avg'"),
):
    """Return daily aggregated readings (sum or average) for a metric."""
    _ensure_schema()
    if agg not in ("sum", "avg"):
        raise HTTPException(status_code=400, detail="agg must be 'sum' or 'avg'")

    df = get_daily_aggregates(asset_id, metric, start, end, agg=agg)
    return {
        "asset_id": asset_id,
        "metric": metric,
        "aggregation": agg,
        "data": [
            {"date": str(row["date"]), "value": float(row["value"])}
            for _, row in df.iterrows()
        ],
    }


@router.get("/inverter/{vendor}/current")
def get_inverter_current(
    vendor: str,
    system_id: str = Query(..., description="System/site identifier"),
):
    """
    Fetch the current power output from a simulated inverter adapter.
    Supported vendors: solaredge, huawei, fronius.
    """
    try:
        adapter = get_adapter(vendor)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc) + f". Supported: {list_supported_vendors()}",
        )
    return adapter.get_current_output(system_id)


@router.get("/inverter/{vendor}/daily")
def get_inverter_daily(
    vendor: str,
    system_id: str = Query(..., description="System/site identifier"),
):
    """Fetch today's energy summary from a simulated inverter adapter."""
    try:
        adapter = get_adapter(vendor)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return adapter.get_daily_summary(system_id)
