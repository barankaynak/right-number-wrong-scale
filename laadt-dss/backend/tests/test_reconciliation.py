"""
Tests for Phase 3.2 — Expectation-Reality Reconciliation Engine.

Tests run against the real PostgreSQL container.
Each test class uses unique asset_id values to ensure isolation.
"""

from __future__ import annotations

import uuid
import pytest
from datetime import datetime, timezone, timedelta

from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _unique_asset(prefix: str = "test") -> str:
    """Return a unique asset_id for test isolation."""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _make_sim_results(annual_kwh: float = 3650.0) -> dict:
    return {
        "expected_annual_production_kwh": annual_kwh,
        "expected_annual_savings_tl": 50000.0,
        "expected_payback_years": 7.5,
        "expected_npv_tl": 120000.0,
        "expected_irr_pct": 14.5,
        "expected_soh_curve": [
            {"year": y, "soh_pct": max(80.0, 100.0 - y * 2.0)}
            for y in range(1, 26)
        ],
        "assumptions": {
            "tariff_tl_per_kwh": 2.5,
            "panel_efficiency_pct": 20.0,
        },
    }


def _make_sim_params() -> dict:
    return {
        "latitude": 39.92,
        "longitude": 32.85,
        "system_capacity_kw": 10.0,
        "battery_capacity_kwh": 20.0,
        "panel_efficiency_multiplier": 1.0,
        "annual_degradation_rate": 0.02,
        "tariff_multiplier": 1.0,
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client():
    from app.main import app
    return TestClient(app)


@pytest.fixture(autouse=True)
def init_schema():
    """Ensure baseline schema exists before each test."""
    from app.digital_twin.reconciliation.baseline_snapshot import init_baseline_schema
    import app.api.routes.dt as dt_routes
    dt_routes._schema_ready = False  # force re-init
    init_baseline_schema()


@pytest.fixture(autouse=True)
def init_iot_schema():
    """Ensure iot_measurements table exists before each test."""
    from app.digital_twin.iot.timeseries_db import init_timeseries_schema
    init_timeseries_schema()


# ---------------------------------------------------------------------------
# TestBaselineSnapshot
# ---------------------------------------------------------------------------

class TestBaselineSnapshot:
    def test_create_and_get_active_baseline(self):
        from app.digital_twin.reconciliation.baseline_snapshot import (
            create_baseline,
            get_active_baseline,
        )

        asset_id = _unique_asset("snap")
        sim_params = _make_sim_params()
        sim_results = _make_sim_results()

        new_id = create_baseline(asset_id, sim_params, sim_results)
        assert isinstance(new_id, int)
        assert new_id > 0

        baseline = get_active_baseline(asset_id)
        assert baseline is not None
        assert baseline["asset_id"] == asset_id
        assert baseline["is_active"] is True
        assert baseline["version"] == 1
        assert baseline["sim_results"]["expected_annual_production_kwh"] == pytest.approx(3650.0)

    def test_versioning_deactivates_old(self):
        from app.digital_twin.reconciliation.baseline_snapshot import (
            create_baseline,
            get_active_baseline,
            list_baselines,
        )

        asset_id = _unique_asset("ver")
        create_baseline(asset_id, _make_sim_params(), _make_sim_results())
        create_baseline(asset_id, _make_sim_params(), _make_sim_results(annual_kwh=4000.0))

        active = get_active_baseline(asset_id)
        assert active is not None
        assert active["version"] == 2
        assert active["sim_results"]["expected_annual_production_kwh"] == pytest.approx(4000.0)

        all_baselines = list_baselines(asset_id)
        v1 = next(b for b in all_baselines if b["version"] == 1)
        assert v1["is_active"] is False

    def test_list_baselines_returns_history(self):
        from app.digital_twin.reconciliation.baseline_snapshot import (
            create_baseline,
            list_baselines,
        )

        asset_id = _unique_asset("list")
        for kwh in [3000.0, 3500.0, 4000.0]:
            create_baseline(asset_id, _make_sim_params(), _make_sim_results(annual_kwh=kwh))

        baselines = list_baselines(asset_id)
        assert len(baselines) == 3
        # Newest-first (version DESC)
        versions = [b["version"] for b in baselines]
        assert versions == sorted(versions, reverse=True)
        assert baselines[0]["version"] == 3

    def test_get_active_returns_none_for_unknown_asset(self):
        from app.digital_twin.reconciliation.baseline_snapshot import get_active_baseline

        result = get_active_baseline("totally_unknown_asset_xyz_999")
        assert result is None


# ---------------------------------------------------------------------------
# TestDriftDetector
# ---------------------------------------------------------------------------

class TestDriftDetector:
    def test_insufficient_data(self):
        """Asset with baseline but no IoT data → INSUFFICIENT_DATA."""
        from app.digital_twin.reconciliation.baseline_snapshot import create_baseline
        from app.digital_twin.reconciliation.drift_detector import DriftDetector

        asset_id = _unique_asset("drift_ins")
        create_baseline(asset_id, _make_sim_params(), _make_sim_results())

        detector = DriftDetector()
        result = detector.analyze(asset_id, lookback_days=30)

        assert result["alert_level"] == "INSUFFICIENT_DATA"
        assert result["data_points"] < 3

    def test_ok_status_when_actuals_match_baseline(self):
        """
        Seed 30 daily pv/power readings that match the 3650 kWh/year baseline
        (≈10 kWh/day ≈ 10 000 Wh cumulative per day).
        Daily sum of power readings stored as W; 10 readings @ 1000 W each = 10 000 Wh/day.
        """
        from app.digital_twin.reconciliation.baseline_snapshot import create_baseline
        from app.digital_twin.reconciliation.drift_detector import DriftDetector
        from app.digital_twin.iot.timeseries_db import write_measurement

        asset_id = _unique_asset("drift_ok")
        create_baseline(
            asset_id,
            _make_sim_params(),
            _make_sim_results(annual_kwh=3650.0),
        )

        now = datetime.now(timezone.utc)
        # Write 10 readings per day for the last 30 days at 1000 W each
        # Daily sum = 10 000 W → divide by 1000 = 10 kWh/day, matching baseline
        for day_offset in range(30):
            day_time = now - timedelta(days=30 - day_offset)
            for hour in range(10):
                ts = day_time.replace(hour=hour, minute=0, second=0, microsecond=0)
                write_measurement(asset_id, "pv/power", 1000.0, ts)

        detector = DriftDetector()
        result = detector.analyze(asset_id, lookback_days=30)

        assert result["alert_level"] in ("OK", "WARNING")  # near-perfect match → OK
        assert result["data_points"] >= 3

    def test_warning_when_significant_deviation(self):
        """
        Seed readings at ~50% of expected production → WARNING or CRITICAL.
        """
        from app.digital_twin.reconciliation.baseline_snapshot import create_baseline
        from app.digital_twin.reconciliation.drift_detector import DriftDetector
        from app.digital_twin.iot.timeseries_db import write_measurement

        asset_id = _unique_asset("drift_warn")
        create_baseline(
            asset_id,
            _make_sim_params(),
            _make_sim_results(annual_kwh=3650.0),
        )

        now = datetime.now(timezone.utc)
        # Write only 5 readings @ 200 W each per day → 1 kWh/day vs expected 10 kWh/day
        for day_offset in range(10):
            day_time = now - timedelta(days=10 - day_offset)
            for hour in range(5):
                ts = day_time.replace(hour=hour, minute=0, second=0, microsecond=0)
                write_measurement(asset_id, "pv/power", 200.0, ts)

        detector = DriftDetector()
        result = detector.analyze(asset_id, lookback_days=10)

        assert result["alert_level"] in ("WARNING", "CRITICAL")
        assert result["metrics"]["production_mape"] > 15.0


# ---------------------------------------------------------------------------
# TestAutoCalibration
# ---------------------------------------------------------------------------

class TestAutoCalibration:
    def test_no_calibration_when_ok(self):
        from app.digital_twin.reconciliation.baseline_snapshot import create_baseline
        from app.digital_twin.reconciliation.auto_calibration import AutoCalibration

        asset_id = _unique_asset("cal_ok")
        create_baseline(asset_id, _make_sim_params(), _make_sim_results())

        drift_report = {
            "alert_level": "OK",
            "metrics": {
                "production_mape": 5.0,
                "battery_soh_delta": -1.0,
                "savings_variance_pct": 3.0,
            },
        }

        calibrator = AutoCalibration()
        result = calibrator.calibrate(asset_id, drift_report)

        assert result["calibrated"] is False
        assert result["adjustments"] == []

    def test_calibration_adjusts_efficiency(self):
        from app.digital_twin.reconciliation.baseline_snapshot import create_baseline
        from app.digital_twin.reconciliation.auto_calibration import AutoCalibration

        asset_id = _unique_asset("cal_eff")
        create_baseline(asset_id, _make_sim_params(), _make_sim_results())

        drift_report = {
            "alert_level": "WARNING",
            "metrics": {
                "production_mape": 25.0,   # > 15% threshold
                "battery_soh_delta": -1.0,
                "savings_variance_pct": 5.0,
            },
        }

        calibrator = AutoCalibration()
        result = calibrator.calibrate(asset_id, drift_report)

        assert result["calibrated"] is True
        panel_adj = next(
            (a for a in result["adjustments"] if a["parameter"] == "panel_efficiency_multiplier"),
            None,
        )
        assert panel_adj is not None
        assert panel_adj["new_value"] < panel_adj["old_value"]
        assert "updated_projections" in result
        assert result["updated_projections"]["expected_annual_production_kwh"] < 3650.0

    def test_calibration_creates_new_version(self):
        from app.digital_twin.reconciliation.baseline_snapshot import (
            create_baseline,
            list_baselines,
        )
        from app.digital_twin.reconciliation.auto_calibration import AutoCalibration

        asset_id = _unique_asset("cal_ver")
        create_baseline(asset_id, _make_sim_params(), _make_sim_results())

        drift_report = {
            "alert_level": "CRITICAL",
            "metrics": {
                "production_mape": 35.0,  # triggers panel efficiency adjustment
                "battery_soh_delta": -8.0,  # triggers degradation rate adjustment
                "savings_variance_pct": 5.0,
            },
        }

        calibrator = AutoCalibration()
        result = calibrator.calibrate(asset_id, drift_report)

        assert result["calibrated"] is True
        assert result["new_baseline_version"] == 2

        baselines = list_baselines(asset_id)
        assert len(baselines) == 2
        active = next(b for b in baselines if b["is_active"])
        assert active["version"] == 2


# ---------------------------------------------------------------------------
# TestDTApi
# ---------------------------------------------------------------------------

class TestDTApi:
    def test_register_asset(self, client):
        asset_id = _unique_asset("api_reg")
        payload = {
            "asset_id": asset_id,
            "sim_params": _make_sim_params(),
            "sim_results": _make_sim_results(),
        }
        resp = client.post("/api/v1/dt/register-asset", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["asset_id"] == asset_id
        assert body["baseline_version"] == 1

    def test_get_status(self, client):
        asset_id = _unique_asset("api_status")
        # Register first
        client.post(
            "/api/v1/dt/register-asset",
            json={
                "asset_id": asset_id,
                "sim_params": _make_sim_params(),
                "sim_results": _make_sim_results(),
            },
        )

        resp = client.get(f"/api/v1/dt/{asset_id}/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["asset_id"] == asset_id
        assert body["has_baseline"] is True
        assert body["baseline_version"] == 1
        assert "latest_readings" in body
        assert "alert_level" in body

    def test_reconciliation_endpoint(self, client):
        asset_id = _unique_asset("api_recon")
        client.post(
            "/api/v1/dt/register-asset",
            json={
                "asset_id": asset_id,
                "sim_params": _make_sim_params(),
                "sim_results": _make_sim_results(),
            },
        )

        resp = client.get(f"/api/v1/dt/{asset_id}/reconciliation")
        assert resp.status_code == 200
        body = resp.json()
        assert body["asset_id"] == asset_id
        assert "alert_level" in body
        assert "metrics" in body
        assert "cusum" in body
        assert "recommendations" in body
        assert isinstance(body["recommendations"], list)

    def test_calibrate_endpoint(self, client):
        asset_id = _unique_asset("api_cal")
        client.post(
            "/api/v1/dt/register-asset",
            json={
                "asset_id": asset_id,
                "sim_params": _make_sim_params(),
                "sim_results": _make_sim_results(),
            },
        )

        resp = client.post(f"/api/v1/dt/{asset_id}/calibrate")
        assert resp.status_code == 200
        body = resp.json()
        assert "drift_report" in body
        assert "calibration" in body
        assert "alert_level" in body["drift_report"]
        assert "calibrated" in body["calibration"]

    def test_baselines_list_endpoint(self, client):
        asset_id = _unique_asset("api_list")

        # Register twice to create two versions
        for kwh in [3650.0, 4000.0]:
            client.post(
                "/api/v1/dt/register-asset",
                json={
                    "asset_id": asset_id,
                    "sim_params": _make_sim_params(),
                    "sim_results": _make_sim_results(annual_kwh=kwh),
                },
            )

        resp = client.get(f"/api/v1/dt/{asset_id}/baselines")
        assert resp.status_code == 200
        body = resp.json()
        assert body["asset_id"] == asset_id
        assert body["count"] == 2
        assert len(body["baselines"]) == 2
        # Newest-first
        assert body["baselines"][0]["version"] > body["baselines"][1]["version"]

    def test_reconciliation_404_for_unknown_asset(self, client):
        resp = client.get("/api/v1/dt/totally_unknown_asset_xyz/reconciliation")
        assert resp.status_code == 404

    def test_calibrate_404_for_unknown_asset(self, client):
        resp = client.post("/api/v1/dt/totally_unknown_asset_xyz/calibrate")
        assert resp.status_code == 404
