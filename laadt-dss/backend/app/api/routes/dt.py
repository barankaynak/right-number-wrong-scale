"""
Digital Twin API routes — Expectation-Reality Reconciliation.

POST /api/v1/dt/register-asset              — register asset + store baseline snapshot
GET  /api/v1/dt/{asset_id}/status           — current DT status
GET  /api/v1/dt/{asset_id}/reconciliation   — full drift analysis
POST /api/v1/dt/{asset_id}/calibrate        — trigger auto-calibration
GET  /api/v1/dt/{asset_id}/baselines        — list all baseline versions
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.digital_twin.reconciliation.baseline_snapshot import (
    init_baseline_schema,
    create_baseline,
    get_active_baseline,
    list_baselines,
)
from app.digital_twin.reconciliation.drift_detector import DriftDetector
from app.digital_twin.reconciliation.auto_calibration import AutoCalibration
from app.digital_twin.iot.timeseries_db import get_latest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/dt", tags=["Digital Twin"])

# Lazy schema init — executed once on first request
_schema_ready = False


def _ensure_schema() -> None:
    global _schema_ready
    if not _schema_ready:
        init_baseline_schema()
        _schema_ready = True


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class RegisterAssetIn(BaseModel):
    asset_id: str
    sim_params: dict        # PV-BESS simulation inputs
    sim_results: dict       # PV-BESS simulation outputs


class AssetStatusOut(BaseModel):
    asset_id: str
    has_baseline: bool
    baseline_version: Optional[int]
    latest_readings: dict   # metric → {value, timestamp}
    alert_level: str        # "OK" / "WARNING" / "CRITICAL" / "NO_DATA" / "INSUFFICIENT_DATA"
    last_reconciliation: Optional[str]


class ReconciliationOut(BaseModel):
    asset_id: str
    alert_level: str
    metrics: dict
    cusum: dict
    recommendations: list[str]
    baseline_version: Optional[int]
    data_points: int
    analysis_timestamp: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/register-asset", summary="Register an asset and store its baseline")
def register_asset(body: RegisterAssetIn):
    """
    Register an asset by storing its pre-investment simulation expectations
    as a baseline snapshot.  A new version is created each time this endpoint
    is called for the same asset_id.
    """
    _ensure_schema()
    new_id = create_baseline(
        asset_id=body.asset_id,
        sim_params=body.sim_params,
        sim_results=body.sim_results,
    )
    baseline = get_active_baseline(body.asset_id)
    return {
        "status": "ok",
        "asset_id": body.asset_id,
        "baseline_id": new_id,
        "baseline_version": baseline["version"] if baseline else None,
        "message": "Asset registered and baseline snapshot stored.",
    }


@router.get("/{asset_id}/status", response_model=AssetStatusOut)
def get_asset_status(asset_id: str):
    """
    Return the current Digital Twin status for an asset.

    Fetches the latest readings for all standard metrics and performs a
    quick 7-day drift analysis.
    """
    _ensure_schema()

    baseline = get_active_baseline(asset_id)
    has_baseline = baseline is not None
    baseline_version = baseline["version"] if baseline else None

    # Fetch latest reading for each standard metric
    standard_metrics = [
        "pv/power", "pv/irradiance",
        "bess/soc", "bess/soh",
        "meter/import", "meter/export",
        "weather/temp",
    ]
    latest_readings: dict = {}
    for metric in standard_metrics:
        value, ts = get_latest(asset_id, metric)
        latest_readings[metric] = {
            "value": value,
            "timestamp": ts.isoformat() if ts else None,
        }

    # Quick drift analysis (7-day lookback)
    if has_baseline:
        detector = DriftDetector()
        drift = detector.analyze(asset_id, lookback_days=7)
        alert_level = drift.get("alert_level", "INSUFFICIENT_DATA")
        last_reconciliation = drift.get("analysis_timestamp")
    else:
        alert_level = "NO_DATA"
        last_reconciliation = None

    return AssetStatusOut(
        asset_id=asset_id,
        has_baseline=has_baseline,
        baseline_version=baseline_version,
        latest_readings=latest_readings,
        alert_level=alert_level,
        last_reconciliation=last_reconciliation,
    )


@router.get("/{asset_id}/reconciliation", response_model=ReconciliationOut)
def get_reconciliation(asset_id: str, lookback_days: int = 30):
    """
    Run a full Expectation-Reality Reconciliation analysis for the asset.

    Returns CUSUM-based drift metrics, alert level, and recommendations.
    """
    _ensure_schema()

    if get_active_baseline(asset_id) is None:
        raise HTTPException(
            status_code=404,
            detail=f"No active baseline found for asset '{asset_id}'. "
                   "Register the asset first via POST /api/v1/dt/register-asset.",
        )

    detector = DriftDetector()
    result = detector.analyze(asset_id, lookback_days=lookback_days)

    return ReconciliationOut(
        asset_id=result["asset_id"],
        alert_level=result["alert_level"],
        metrics=result["metrics"],
        cusum=result["cusum"],
        recommendations=result["recommendations"],
        baseline_version=result.get("baseline_version"),
        data_points=result["data_points"],
        analysis_timestamp=result["analysis_timestamp"],
    )


@router.post("/{asset_id}/calibrate", summary="Trigger auto-calibration")
def calibrate_asset(asset_id: str, lookback_days: int = 30):
    """
    Run drift detection and, if drift is detected, automatically adjust
    model parameters and create a new baseline version.
    """
    _ensure_schema()

    if get_active_baseline(asset_id) is None:
        raise HTTPException(
            status_code=404,
            detail=f"No active baseline found for asset '{asset_id}'.",
        )

    # Step 1: detect current drift
    detector = DriftDetector()
    drift_report = detector.analyze(asset_id, lookback_days=lookback_days)

    # Step 2: calibrate
    calibrator = AutoCalibration()
    calibration_result = calibrator.calibrate(asset_id, drift_report)

    return {
        "drift_report": {
            "alert_level": drift_report["alert_level"],
            "metrics": drift_report["metrics"],
            "data_points": drift_report["data_points"],
        },
        "calibration": calibration_result,
    }


@router.get("/{asset_id}/baselines", summary="List all baseline versions")
def get_baselines(asset_id: str):
    """
    Return all stored baseline versions for an asset, newest first.
    """
    _ensure_schema()

    baselines = list_baselines(asset_id)
    return {
        "asset_id": asset_id,
        "count": len(baselines),
        "baselines": [
            {
                "id": b["id"],
                "version": b["version"],
                "is_active": b["is_active"],
                "created_at": b["created_at"],
            }
            for b in baselines
        ],
    }
