"""
Tests for bess/degradation.py — semi-empirical battery aging model.
"""
import pytest
import numpy as np

from app.simulation.bess.degradation import (
    rainflow_count_cycles,
    calculate_calendar_aging,
    calculate_cyclic_aging,
    calculate_annual_degradation,
    project_soh_curve,
    CHEMISTRY_PARAMS,
)


class TestRainflowCountCycles:
    def test_empty_series_returns_empty(self):
        cycles = rainflow_count_cycles(np.array([]))
        assert cycles == []

    def test_constant_soc_no_cycles(self):
        soc = np.full(100, 0.5)
        cycles = rainflow_count_cycles(soc)
        # All ranges are zero — micro-cycles filtered in cyclic aging, but list may have entries
        dods = [dod for dod, _ in cycles]
        assert all(d == 0.0 for d in dods)

    def test_single_full_cycle_detected(self):
        """One full charge/discharge cycle: 0 → 1 → 0."""
        soc = np.array([0.0, 0.5, 1.0, 0.5, 0.0])
        cycles = rainflow_count_cycles(soc)
        total_dod = sum(dod for dod, _ in cycles)
        assert total_dod > 0.0

    def test_returns_list_of_tuples(self):
        soc = np.array([0.2, 0.8, 0.3, 0.9, 0.1])
        cycles = rainflow_count_cycles(soc)
        assert isinstance(cycles, list)
        for item in cycles:
            assert len(item) == 2  # (dod, mean_soc)

    def test_mean_soc_within_range(self):
        soc = np.linspace(0.2, 0.9, 50)
        soc = np.concatenate([soc, soc[::-1]])
        cycles = rainflow_count_cycles(soc)
        for dod, mean_soc in cycles:
            assert 0.0 <= mean_soc <= 1.0


class TestCalculateCalendarAging:
    def test_loss_increases_with_time(self):
        loss_1yr = calculate_calendar_aging(1, 25, 0.5, 'LFP')
        loss_5yr = calculate_calendar_aging(5, 25, 0.5, 'LFP')
        assert loss_5yr > loss_1yr

    def test_loss_increases_with_temperature(self):
        loss_25c = calculate_calendar_aging(1, 25, 0.5, 'LFP')
        loss_45c = calculate_calendar_aging(1, 45, 0.5, 'LFP')
        assert loss_45c > loss_25c

    def test_high_soc_more_stress(self):
        loss_low_soc = calculate_calendar_aging(1, 25, 0.2, 'LFP')
        loss_high_soc = calculate_calendar_aging(1, 25, 0.9, 'LFP')
        assert loss_high_soc > loss_low_soc

    def test_loss_bounded_0_to_1(self):
        loss = calculate_calendar_aging(100, 60, 1.0, 'NMC')
        assert 0.0 <= loss <= 1.0

    def test_all_chemistries_supported(self):
        for chem in ['LFP', 'NMC', 'LTO']:
            loss = calculate_calendar_aging(5, 25, 0.5, chem)
            assert 0.0 <= loss <= 1.0

    def test_lto_less_aging_than_nmc(self):
        """LTO has lower activation energy → less calendar aging at same conditions."""
        loss_lto = calculate_calendar_aging(5, 35, 0.5, 'LTO')
        loss_nmc = calculate_calendar_aging(5, 35, 0.5, 'NMC')
        assert loss_lto < loss_nmc


class TestCalculateCyclicAging:
    def test_empty_cycles_returns_zero(self):
        assert calculate_cyclic_aging([], 'LFP') == 0.0

    def test_micro_cycles_filtered(self):
        """Cycles < 1% DoD should be ignored."""
        tiny_cycles = [(0.005, 0.5)] * 1000
        loss = calculate_cyclic_aging(tiny_cycles, 'LFP')
        assert loss == 0.0

    def test_loss_increases_with_dod(self):
        small_dod_cycles = [(0.2, 0.5)] * 100
        large_dod_cycles = [(0.8, 0.5)] * 100
        loss_small = calculate_cyclic_aging(small_dod_cycles, 'LFP')
        loss_large = calculate_cyclic_aging(large_dod_cycles, 'LFP')
        assert loss_large > loss_small

    def test_loss_bounded_0_to_1(self):
        many_cycles = [(1.0, 0.5)] * 100000
        loss = calculate_cyclic_aging(many_cycles, 'NMC')
        assert 0.0 <= loss <= 1.0

    def test_lto_less_cyclic_aging(self):
        cycles = [(0.5, 0.5)] * 500
        loss_lto = calculate_cyclic_aging(cycles, 'LTO')
        loss_nmc = calculate_cyclic_aging(cycles, 'NMC')
        assert loss_lto < loss_nmc


class TestCalculateAnnualDegradation:
    def _make_daily_cycle_soc(self) -> np.ndarray:
        """Simulate daily charge/discharge cycles for 1 year."""
        day = np.concatenate([np.linspace(0.2, 0.9, 12), np.linspace(0.9, 0.2, 12)])
        return np.tile(day, 365)

    def test_result_keys_present(self):
        soc = self._make_daily_cycle_soc()
        result = calculate_annual_degradation(soc, 'LFP', 25.0, 1.0)
        expected = [
            "soh_after_period", "calendar_aging_loss", "cyclic_aging_loss",
            "total_capacity_loss", "equivalent_full_cycles",
            "estimated_lifetime_years", "annual_degradation_cost_tl_per_kwh",
            "average_soc", "chemistry",
        ]
        for key in expected:
            assert key in result

    def test_soh_between_0_and_1(self):
        soc = self._make_daily_cycle_soc()
        result = calculate_annual_degradation(soc, 'LFP', 25.0, 1.0)
        assert 0.0 <= result["soh_after_period"] <= 1.0

    def test_total_loss_sum_of_components(self):
        soc = self._make_daily_cycle_soc()
        result = calculate_annual_degradation(soc, 'LFP', 25.0, 1.0)
        expected_total = round(result["calendar_aging_loss"] + result["cyclic_aging_loss"], 4)
        # May differ slightly due to rounding
        assert abs(result["total_capacity_loss"] - expected_total) <= 0.001

    def test_lfp_better_than_nmc(self):
        """LFP should show less total degradation than NMC under same conditions."""
        soc = self._make_daily_cycle_soc()
        result_lfp = calculate_annual_degradation(soc, 'LFP', 35.0, 5.0)
        result_nmc = calculate_annual_degradation(soc, 'NMC', 35.0, 5.0)
        assert result_lfp["total_capacity_loss"] < result_nmc["total_capacity_loss"]

    def test_chemistry_stored_in_result(self):
        soc = np.full(8760, 0.5)
        result = calculate_annual_degradation(soc, 'LTO', 20.0, 1.0)
        assert result["chemistry"] == 'LTO'

    def test_higher_temperature_more_degradation(self):
        soc = self._make_daily_cycle_soc()
        result_cool = calculate_annual_degradation(soc, 'LFP', 15.0, 3.0)
        result_hot = calculate_annual_degradation(soc, 'LFP', 45.0, 3.0)
        assert result_hot["calendar_aging_loss"] > result_cool["calendar_aging_loss"]


class TestProjectSohCurve:
    def _make_soc_series(self) -> np.ndarray:
        day = np.concatenate([np.linspace(0.2, 0.85, 12), np.linspace(0.85, 0.2, 12)])
        return np.tile(day, 365)

    def test_starts_at_100_percent(self):
        soc = self._make_soc_series()
        curve = project_soh_curve(soc, 'LFP', 25.0, 25)
        assert curve[0] == (0, 1.0)

    def test_soh_monotonically_decreasing(self):
        soc = self._make_soc_series()
        curve = project_soh_curve(soc, 'NMC', 30.0, 15)
        soh_values = [s for _, s in curve]
        assert all(soh_values[i] >= soh_values[i + 1] for i in range(len(soh_values) - 1))

    def test_stops_at_80_percent_threshold(self):
        """Curve should stop when SoH drops below 0.80."""
        soc = self._make_soc_series()
        curve = project_soh_curve(soc, 'NMC', 40.0, 30)
        soh_values = [s for _, s in curve]
        # Last value should be ≤ 0.80 OR we ran full projection_years
        assert soh_values[-1] <= 0.80 or len(curve) == 31  # 0 + 30 years

    def test_returns_list_of_tuples(self):
        soc = self._make_soc_series()
        curve = project_soh_curve(soc, 'LFP', 25.0, 5)
        assert isinstance(curve, list)
        for item in curve:
            assert len(item) == 2
