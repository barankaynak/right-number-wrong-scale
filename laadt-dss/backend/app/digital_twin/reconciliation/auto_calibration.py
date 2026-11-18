"""
AutoCalibration — adjusts model parameters when drift is detected.

Given a drift_report (from DriftDetector.analyze), infers which parameter
is most likely causing the deviation and updates the active baseline with
recalculated forward projections.

Calibration logic (heuristics):
  - production_mape > 15%  → adjust panel_efficiency
  - battery_soh_delta < -5 → adjust annual_degradation_rate
  - savings_variance_pct > 20% → adjust tariff_multiplier

After parameter adjustment, re-runs a simplified financial projection
(no full pvlib re-run — uses scaling factors for speed).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from app.digital_twin.reconciliation.baseline_snapshot import (
    get_active_baseline,
    create_baseline,
)

logger = logging.getLogger(__name__)

# Calibration trigger thresholds
_PRODUCTION_MAPE_THRESHOLD = 15.0   # %
_SOH_DELTA_THRESHOLD = -5.0          # percentage points
_SAVINGS_VARIANCE_THRESHOLD = 20.0  # %


class AutoCalibration:
    """
    Adjusts simulation model parameters based on observed drift.

    All adjustments are heuristic scaling factors — no full physics
    re-simulation is performed; instead, existing baseline outputs are
    scaled to reflect updated expectations.
    """

    def calibrate(self, asset_id: str, drift_report: dict) -> dict:
        """
        Inspect the drift report and apply parameter adjustments if needed.

        Args:
            asset_id:     Unique asset identifier.
            drift_report: Output from DriftDetector.analyze().

        Returns:
            A dict with calibration results (see module docstring).
        """
        now = datetime.now(timezone.utc)

        alert_level = drift_report.get("alert_level", "OK")

        # No calibration needed when system is performing as expected
        if alert_level in ("OK", "INSUFFICIENT_DATA", "NO_DATA"):
            return {
                "asset_id": asset_id,
                "calibrated": False,
                "adjustments": [],
                "updated_projections": {},
                "new_baseline_version": None,
                "calibration_timestamp": now.isoformat(),
            }

        baseline = get_active_baseline(asset_id)
        if baseline is None:
            logger.warning(
                "AutoCalibration: no active baseline for asset '%s'", asset_id
            )
            return {
                "asset_id": asset_id,
                "calibrated": False,
                "adjustments": [],
                "updated_projections": {},
                "new_baseline_version": None,
                "calibration_timestamp": now.isoformat(),
            }

        sim_params: dict = dict(baseline["sim_params"])
        sim_results: dict = dict(baseline["sim_results"])
        metrics: dict = drift_report.get("metrics", {})

        adjustments: list[dict] = []

        # ------------------------------------------------------------------
        # 1. Panel efficiency adjustment
        # ------------------------------------------------------------------
        production_mape = float(metrics.get("production_mape") or 0.0)
        panel_efficiency_multiplier = 1.0

        if production_mape > _PRODUCTION_MAPE_THRESHOLD:
            old_multiplier = float(sim_params.get("panel_efficiency_multiplier", 1.0))
            new_multiplier = 1.0 - production_mape / 100.0
            # Guard against absurd values
            new_multiplier = max(0.5, min(1.0, new_multiplier))

            sim_params["panel_efficiency_multiplier"] = new_multiplier
            panel_efficiency_multiplier = new_multiplier / old_multiplier if old_multiplier else new_multiplier

            adjustments.append(
                {
                    "parameter": "panel_efficiency_multiplier",
                    "old_value": round(old_multiplier, 6),
                    "new_value": round(new_multiplier, 6),
                    "reason": (
                        f"PV production MAPE of {production_mape:.1f}% exceeds "
                        f"{_PRODUCTION_MAPE_THRESHOLD}% threshold. "
                        "Reduced panel efficiency multiplier."
                    ),
                }
            )

        # ------------------------------------------------------------------
        # 2. Battery degradation rate adjustment
        # ------------------------------------------------------------------
        battery_soh_delta = metrics.get("battery_soh_delta")
        if battery_soh_delta is not None:
            battery_soh_delta = float(battery_soh_delta)
            if battery_soh_delta < _SOH_DELTA_THRESHOLD:
                old_rate = float(sim_params.get("annual_degradation_rate", 0.02))
                new_rate = old_rate * 1.10  # increase degradation estimate by 10%

                sim_params["annual_degradation_rate"] = round(new_rate, 6)

                adjustments.append(
                    {
                        "parameter": "annual_degradation_rate",
                        "old_value": round(old_rate, 6),
                        "new_value": round(new_rate, 6),
                        "reason": (
                            f"Battery SOH delta of {battery_soh_delta:.1f} pp is below "
                            f"{_SOH_DELTA_THRESHOLD} pp threshold. "
                            "Increased annual degradation rate by 10%."
                        ),
                    }
                )

        # ------------------------------------------------------------------
        # 3. Tariff multiplier adjustment
        # ------------------------------------------------------------------
        savings_variance_pct = metrics.get("savings_variance_pct")
        tariff_multiplier = 1.0

        if savings_variance_pct is not None:
            savings_variance_pct = float(savings_variance_pct)
            if abs(savings_variance_pct) > _SAVINGS_VARIANCE_THRESHOLD:
                old_tariff_mult = float(sim_params.get("tariff_multiplier", 1.0))

                # actual_savings / expected_savings ratio
                # savings_variance_pct = (actual - expected) / expected * 100
                new_tariff_mult = old_tariff_mult * (1.0 + savings_variance_pct / 100.0)
                new_tariff_mult = max(0.5, min(2.0, new_tariff_mult))

                tariff_multiplier = new_tariff_mult / old_tariff_mult if old_tariff_mult else 1.0
                sim_params["tariff_multiplier"] = round(new_tariff_mult, 6)

                adjustments.append(
                    {
                        "parameter": "tariff_multiplier",
                        "old_value": round(old_tariff_mult, 6),
                        "new_value": round(new_tariff_mult, 6),
                        "reason": (
                            f"Savings variance of {savings_variance_pct:.1f}% exceeds "
                            f"{_SAVINGS_VARIANCE_THRESHOLD}% threshold. "
                            "Adjusted tariff multiplier."
                        ),
                    }
                )

        if not adjustments:
            # Drift reported but no specific heuristic triggered
            return {
                "asset_id": asset_id,
                "calibrated": False,
                "adjustments": [],
                "updated_projections": {},
                "new_baseline_version": None,
                "calibration_timestamp": now.isoformat(),
            }

        # ------------------------------------------------------------------
        # 4. Recompute forward projections using scaling factors
        # ------------------------------------------------------------------
        old_production = float(sim_results.get("expected_annual_production_kwh", 0) or 0)
        old_savings = float(sim_results.get("expected_annual_savings_tl", 0) or 0)
        old_payback = float(sim_results.get("expected_payback_years", 1) or 1)
        old_npv = float(sim_results.get("expected_npv_tl", 0) or 0)
        old_irr = float(sim_results.get("expected_irr_pct", 0) or 0)

        new_production = old_production * panel_efficiency_multiplier
        new_savings = old_savings * tariff_multiplier
        # Payback decreases when savings increase
        new_payback = old_payback / tariff_multiplier if tariff_multiplier > 0 else old_payback
        # NPV scales approximately with savings ratio
        new_npv = old_npv * tariff_multiplier
        # Rough IRR adjustment: scale proportional to savings change
        new_irr = old_irr * tariff_multiplier

        updated_projections = {
            "expected_annual_production_kwh": round(new_production, 2),
            "expected_annual_savings_tl": round(new_savings, 2),
            "expected_payback_years": round(new_payback, 4),
            "expected_npv_tl": round(new_npv, 2),
        }

        # Update sim_results with new projections
        new_sim_results = dict(sim_results)
        new_sim_results.update(updated_projections)
        new_sim_results["expected_irr_pct"] = round(new_irr, 4)

        # ------------------------------------------------------------------
        # 5. Persist new baseline version
        # ------------------------------------------------------------------
        new_id = create_baseline(asset_id, sim_params, new_sim_results)
        new_baseline = get_active_baseline(asset_id)
        new_version = new_baseline["version"] if new_baseline else None

        logger.info(
            "AutoCalibration completed for asset '%s': %d adjustment(s), "
            "new baseline v%s (id=%d)",
            asset_id,
            len(adjustments),
            new_version,
            new_id,
        )

        return {
            "asset_id": asset_id,
            "calibrated": True,
            "adjustments": adjustments,
            "updated_projections": updated_projections,
            "new_baseline_version": new_version,
            "calibration_timestamp": now.isoformat(),
        }
