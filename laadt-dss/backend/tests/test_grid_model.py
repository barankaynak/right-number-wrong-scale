"""
Tests for grid_model.py — Newton-Raphson load flow and hosting capacity analysis.
"""
import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
import numpy as np

from app.simulation.grid.grid_model import (
    create_distribution_network,
    create_synthetic_radial_network,
    simulate_grid_impact,
    run_penetration_analysis,
    simulate_transformer_deferral,
)


def _synthetic(*args, **kwargs):
    return create_synthetic_radial_network()


class TestCreateDistributionNetwork:
    def test_simbench_failure_raises_no_silent_fallback(self):
        """A23: SimBench yüklenemezse sentetik ağa SESSİZCE düşülmez — hata yükselir."""
        with patch("simbench.get_simbench_net", side_effect=Exception("Not available")):
            with pytest.raises(Exception):
                create_distribution_network()

    def test_fallback_network_created_when_simbench_fails(self):
        """create_distribution_network explicit synthetic radial network (test fixture)."""
        net = create_synthetic_radial_network()
        assert net is not None
        assert len(net.bus) >= 4
        assert len(net.load) >= 3
        assert len(net.line) >= 3
        assert len(net.ext_grid) >= 1

    def test_fallback_network_bus_voltage(self):
        """Fallback network uses 0.4 kV LV buses."""
        net = create_synthetic_radial_network()
        assert all(net.bus["vn_kv"] == 0.4)

    def test_fallback_network_line_parameters(self):
        """Fallback network uses explicit NAYY 4x50 SE equivalent line parameters."""
        net = create_synthetic_radial_network()
        # Lines created via create_line_from_parameters have std_type=None
        assert all(net.line["std_type"].isna())
        # Check resistance is in NAYY 4x50 SE range (~0.641 Ω/km)
        assert all(net.line["r_ohm_per_km"].between(0.5, 0.8))


class TestSimulateGridImpact:
    def _run_with_fallback(self, **kwargs):
        """Helper: runs simulate_grid_impact using fallback network."""
        with patch("app.simulation.grid.grid_model.create_distribution_network", side_effect=_synthetic):
            return simulate_grid_impact(**kwargs)

    def test_zero_pv_returns_converged(self):
        result = self._run_with_fallback(pv_penetration_pct=0.0)
        assert result["converged"] is True

    def test_low_pv_no_voltage_violation(self):
        """Low PV penetration should not cause voltage violation."""
        result = self._run_with_fallback(pv_penetration_pct=10.0)
        assert result["converged"] is True
        assert result["max_voltage_pu"] <= 1.10  # Reasonable bound

    def test_result_keys_present(self):
        result = self._run_with_fallback(pv_penetration_pct=30.0)
        expected_keys = [
            "converged", "pv_penetration_pct", "bess_penetration_pct",
            "max_voltage_pu", "min_voltage_pu", "voltage_violation",
            "max_line_loading_pct", "line_overload", "total_losses_mw",
            "reverse_power_flow",
        ]
        for key in expected_keys:
            assert key in result, f"Missing key: {key}"

    def test_pv_penetration_stored_in_result(self):
        result = self._run_with_fallback(pv_penetration_pct=50.0)
        assert result["pv_penetration_pct"] == 50.0

    def test_bess_reduces_net_injection(self):
        """BESS penetration should reduce reverse power flow tendency."""
        result_no_bess = self._run_with_fallback(pv_penetration_pct=80.0, bess_penetration_pct=0.0)
        result_with_bess = self._run_with_fallback(pv_penetration_pct=80.0, bess_penetration_pct=50.0)
        # With BESS absorbing, max voltage should be lower or equal
        if result_no_bess["converged"] and result_with_bess["converged"]:
            assert result_with_bess["max_voltage_pu"] <= result_no_bess["max_voltage_pu"] + 0.01

    def test_load_growth_increases_loading(self):
        result_base = self._run_with_fallback(pv_penetration_pct=0.0, load_growth_pct=0.0)
        result_grown = self._run_with_fallback(pv_penetration_pct=0.0, load_growth_pct=50.0)
        if result_base["converged"] and result_grown["converged"]:
            assert result_grown["max_line_loading_pct"] >= result_base["max_line_loading_pct"]

    def test_voltage_values_are_physical(self):
        result = self._run_with_fallback(pv_penetration_pct=20.0)
        if result["converged"]:
            assert 0.5 <= result["min_voltage_pu"] <= result["max_voltage_pu"] <= 1.5

    def test_losses_non_negative(self):
        result = self._run_with_fallback(pv_penetration_pct=30.0)
        if result["converged"]:
            assert result["total_losses_mw"] >= 0.0


class TestRunPenetrationAnalysis:
    def test_returns_dataframe(self):
        with patch("app.simulation.grid.grid_model.create_distribution_network", side_effect=_synthetic):
            df = run_penetration_analysis(levels=[0, 50, 100])
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 3

    def test_dataframe_columns(self):
        with patch("app.simulation.grid.grid_model.create_distribution_network", side_effect=_synthetic):
            df = run_penetration_analysis(levels=[0, 30])
        assert "pv_penetration_pct" in df.columns
        assert "max_voltage_pu" in df.columns
        assert "voltage_violation" in df.columns

    def test_hosting_capacity_attr(self):
        """hosting_capacity_pct attribute is set on the DataFrame."""
        with patch("app.simulation.grid.grid_model.create_distribution_network", side_effect=_synthetic):
            df = run_penetration_analysis(levels=[0, 10, 20, 30])
        assert "hosting_capacity_pct" in df.attrs
        assert 0.0 <= df.attrs["hosting_capacity_pct"] <= 100.0

    def test_ascending_penetration_levels(self):
        with patch("app.simulation.grid.grid_model.create_distribution_network", side_effect=_synthetic):
            df = run_penetration_analysis(levels=[0, 25, 50])
        assert list(df["pv_penetration_pct"]) == [0, 25, 50]


class TestSimulateTransformerDeferral:
    def test_returns_expected_keys(self):
        with patch("app.simulation.grid.grid_model.create_distribution_network", side_effect=_synthetic):
            result = simulate_transformer_deferral(
                pv_penetration_pct=30.0,
                bess_penetration_pct=20.0,
                years=5,
                annual_load_growth_pct=10.0,
            )
        expected = [
            "years_without_der", "years_with_der", "deferral_years",
            "trafo_upgrade_cost_tl", "npv_deferral_benefit_tl",
        ]
        for key in expected:
            assert key in result

    def test_deferral_years_non_negative(self):
        with patch("app.simulation.grid.grid_model.create_distribution_network", side_effect=_synthetic):
            result = simulate_transformer_deferral(years=5, annual_load_growth_pct=10.0)
        assert result["deferral_years"] >= 0

    def test_trafo_upgrade_cost_fixed(self):
        with patch("app.simulation.grid.grid_model.create_distribution_network", side_effect=_synthetic):
            result = simulate_transformer_deferral(years=3)
        assert result["trafo_upgrade_cost_tl"] == 500_000
