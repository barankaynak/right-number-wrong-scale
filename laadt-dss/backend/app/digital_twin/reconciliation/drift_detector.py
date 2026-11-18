"""
DriftDetector — compares IoT actuals against baseline expectations.

Uses CUSUM (Cumulative Sum) control chart to detect systematic deviations.

Alert thresholds:
    OK       : all metrics within 15%
    WARNING  : any metric between 15-30%
    CRITICAL : any metric exceeding 30%
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from app.digital_twin.reconciliation.baseline_snapshot import get_active_baseline
from app.digital_twin.iot.timeseries_db import (
    read_timeseries,
    get_latest,
    get_daily_aggregates,
)

logger = logging.getLogger(__name__)

# CUSUM alarm threshold
_CUSUM_ALARM_THRESHOLD = 5.0

# Deviation thresholds (percentages)
_WARNING_THRESHOLD = 15.0
_CRITICAL_THRESHOLD = 30.0

# Minimum number of daily data points required for analysis
_MIN_DATA_DAYS = 3


class DriftDetector:
    """
    Detects systematic drift between IoT actuals and simulation baselines.

    Implements CUSUM control charts for production drift detection and
    computes MAPE, SOH delta, and savings variance metrics.
    """

    def analyze(self, asset_id: str, lookback_days: int = 30) -> dict:
        """
        Analyze drift between actuals and baseline expectations.

        Args:
            asset_id:      Unique asset identifier.
            lookback_days: Number of past days to include in analysis.

        Returns:
            A dict with keys:
              asset_id, alert_level, lookback_days, analysis_timestamp,
              metrics, cusum, recommendations, baseline_version, data_points
        """
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=lookback_days)

        baseline = get_active_baseline(asset_id)
        if baseline is None:
            return self._no_baseline_response(asset_id, lookback_days, now)

        sim_results = baseline["sim_results"]
        baseline_version = baseline["version"]

        # ----------------------------------------------------------------
        # Fetch daily PV production actuals
        # ----------------------------------------------------------------
        daily_df = get_daily_aggregates(asset_id, "pv/power", start, now, agg="sum")

        # Convert Wh sums to kWh
        # pv/power is stored in Watts; daily sum of hourly readings ÷ 1000 = kWh
        # (sum of power values at whatever sampling rate; we treat it as Wh → kWh)
        if not daily_df.empty:
            daily_df["value_kwh"] = daily_df["value"] / 1000.0

        data_points = len(daily_df)

        if data_points < _MIN_DATA_DAYS:
            return {
                "asset_id": asset_id,
                "alert_level": "INSUFFICIENT_DATA",
                "lookback_days": lookback_days,
                "analysis_timestamp": now.isoformat(),
                "metrics": {},
                "cusum": {"production_cusum_score": 0.0, "cusum_alarm": False},
                "recommendations": [
                    "Insufficient data: fewer than 3 days of measurements available. "
                    "Ensure IoT sensors are correctly connected and publishing data."
                ],
                "baseline_version": baseline_version,
                "data_points": data_points,
            }

        # ----------------------------------------------------------------
        # Compute expected daily production
        # ----------------------------------------------------------------
        expected_annual_kwh = float(
            sim_results.get("expected_annual_production_kwh", 0) or 0
        )
        expected_daily_kwh = expected_annual_kwh / 365.0
        expected_period_kwh = expected_daily_kwh * lookback_days

        actual_period_kwh = float(daily_df["value_kwh"].sum()) if not daily_df.empty else 0.0

        production_mape = (
            abs(actual_period_kwh - expected_period_kwh) / max(expected_period_kwh, 1e-9) * 100.0
        )

        # ----------------------------------------------------------------
        # CUSUM for production
        # ----------------------------------------------------------------
        cusum_score, cusum_alarm = self._compute_cusum(
            daily_actuals=daily_df["value_kwh"].tolist() if not daily_df.empty else [],
            expected_daily=expected_daily_kwh,
        )

        # ----------------------------------------------------------------
        # Battery SOH delta
        # ----------------------------------------------------------------
        battery_soh_delta = self._compute_soh_delta(asset_id, sim_results)

        # ----------------------------------------------------------------
        # Savings variance
        # ----------------------------------------------------------------
        savings_variance_pct = self._compute_savings_variance(
            asset_id, sim_results, start, now, lookback_days
        )

        # ----------------------------------------------------------------
        # Alert level
        # ----------------------------------------------------------------
        max_deviation = max(
            production_mape,
            abs(battery_soh_delta) if battery_soh_delta is not None else 0.0,
            abs(savings_variance_pct) if savings_variance_pct is not None else 0.0,
        )

        if max_deviation >= _CRITICAL_THRESHOLD:
            alert_level = "CRITICAL"
        elif max_deviation >= _WARNING_THRESHOLD:
            alert_level = "WARNING"
        else:
            alert_level = "OK"

        # ----------------------------------------------------------------
        # Recommendations
        # ----------------------------------------------------------------
        recommendations = self._build_recommendations(
            alert_level=alert_level,
            production_mape=production_mape,
            battery_soh_delta=battery_soh_delta,
            savings_variance_pct=savings_variance_pct,
            cusum_alarm=cusum_alarm,
        )

        return {
            "asset_id": asset_id,
            "alert_level": alert_level,
            "lookback_days": lookback_days,
            "analysis_timestamp": now.isoformat(),
            "metrics": {
                "production_mape": round(production_mape, 4),
                "battery_soh_delta": round(battery_soh_delta, 4) if battery_soh_delta is not None else None,
                "savings_variance_pct": round(savings_variance_pct, 4) if savings_variance_pct is not None else None,
            },
            "cusum": {
                "production_cusum_score": round(cusum_score, 4),
                "cusum_alarm": cusum_alarm,
            },
            "recommendations": recommendations,
            "baseline_version": baseline_version,
            "data_points": data_points,
        }

    # ----------------------------------------------------------------
    # Private helpers
    # ----------------------------------------------------------------

    def _compute_cusum(
        self, daily_actuals: list[float], expected_daily: float
    ) -> tuple[float, bool]:
        """
        Compute CUSUM score for production.

        Score = Σ(actual_i - expected_i) / expected_mean

        Returns (score, alarm_bool).
        """
        if not daily_actuals or expected_daily <= 0:
            return 0.0, False

        cusum_score = sum(
            (actual - expected_daily) / expected_daily
            for actual in daily_actuals
        )
        alarm = abs(cusum_score) > _CUSUM_ALARM_THRESHOLD
        return cusum_score, alarm

    def _compute_soh_delta(self, asset_id: str, sim_results: dict) -> Optional[float]:
        """
        Compute actual_soh - expected_soh in percentage points.

        Returns None if no SOH data is available.
        """
        actual_soh, _ = get_latest(asset_id, "bess/soh")
        if actual_soh is None:
            return None

        # Expected SOH at this point: use year 1 value from soh_curve if available
        soh_curve = sim_results.get("expected_soh_curve", [])
        expected_soh = 100.0  # default: brand new
        if soh_curve:
            # Take the first year entry as our current expectation baseline
            first_entry = soh_curve[0] if isinstance(soh_curve[0], dict) else {}
            expected_soh = float(first_entry.get("soh_pct", 100.0))

        return float(actual_soh) - expected_soh

    def _compute_savings_variance(
        self,
        asset_id: str,
        sim_results: dict,
        start: datetime,
        now: datetime,
        lookback_days: int,
    ) -> Optional[float]:
        """
        Compute (actual_savings - expected_savings) / expected_savings * 100.

        Approximates actual savings as (meter/export - meter/import) proxy.
        Returns None if insufficient meter data.
        """
        export_df = get_daily_aggregates(asset_id, "meter/export", start, now, agg="sum")
        if export_df.empty:
            return None

        actual_export_kwh = float(export_df["value"].sum()) / 1000.0  # W → kWh

        expected_annual_savings = float(
            sim_results.get("expected_annual_savings_tl", 0) or 0
        )
        if expected_annual_savings <= 0:
            return None

        # Scale to lookback period (use as proportion proxy, dimensionless)
        expected_period_savings = expected_annual_savings / 365.0 * lookback_days

        # actual_export_kwh is in energy, not TL — use it as a ratio proxy
        expected_annual_kwh = float(
            sim_results.get("expected_annual_production_kwh", 1) or 1
        )
        expected_period_kwh = expected_annual_kwh / 365.0 * lookback_days

        # Savings variance based on energy ratio
        return (actual_export_kwh - expected_period_kwh) / max(expected_period_kwh, 1e-9) * 100.0

    def _build_recommendations(
        self,
        alert_level: str,
        production_mape: float,
        battery_soh_delta: Optional[float],
        savings_variance_pct: Optional[float],
        cusum_alarm: bool,
    ) -> list[str]:
        recs: list[str] = []

        if alert_level == "OK":
            recs.append("System is performing within expected parameters. No action required.")
            return recs

        if production_mape > _CRITICAL_THRESHOLD:
            recs.append(
                f"PV production is {production_mape:.1f}% below expectation — inspect panel soiling, "
                "shading, or inverter faults. Consider re-calibrating the model."
            )
        elif production_mape > _WARNING_THRESHOLD:
            recs.append(
                f"PV production deviation of {production_mape:.1f}% detected. "
                "Schedule panel cleaning and review inverter logs."
            )

        if battery_soh_delta is not None and battery_soh_delta < -5.0:
            recs.append(
                f"Battery SOH is {abs(battery_soh_delta):.1f} pp below expectation. "
                "Evaluate charge/discharge patterns and ambient temperature history."
            )

        if savings_variance_pct is not None and abs(savings_variance_pct) > _WARNING_THRESHOLD:
            recs.append(
                f"Energy export variance of {savings_variance_pct:.1f}% from baseline. "
                "Verify tariff structure and meter calibration."
            )

        if cusum_alarm:
            recs.append(
                "CUSUM alarm triggered: systematic production under-performance detected. "
                "Initiate root-cause analysis."
            )

        if not recs:
            recs.append(
                f"Overall deviation ({alert_level}) detected. "
                "Review system logs and compare against seasonal expectations."
            )

        return recs

    def _no_baseline_response(
        self, asset_id: str, lookback_days: int, now: datetime
    ) -> dict:
        return {
            "asset_id": asset_id,
            "alert_level": "INSUFFICIENT_DATA",
            "lookback_days": lookback_days,
            "analysis_timestamp": now.isoformat(),
            "metrics": {},
            "cusum": {"production_cusum_score": 0.0, "cusum_alarm": False},
            "recommendations": [
                "No active baseline found for this asset. "
                "Register the asset and provide simulation results first."
            ],
            "baseline_version": None,
            "data_points": 0,
        }
