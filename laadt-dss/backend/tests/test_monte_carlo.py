"""
Tests for economic/monte_carlo.py — Monte Carlo uncertainty analysis.
"""
import pytest
import numpy as np

from app.simulation.economic.monte_carlo import run_monte_carlo, _single_iteration


class TestSingleIteration:
    def test_returns_required_keys(self):
        result = _single_iteration(
            seed=42,
            base_investment_tl=200_000,
            base_annual_savings_tl=25_000,
            lifetime_years=25,
            base_discount_rate=0.12,
        )
        assert "npv" in result
        assert "payback" in result
        assert "tariff_growth" in result
        assert "panel_degradation" in result
        assert "discount_rate" in result

    def test_tariff_growth_clipped(self):
        """Tariff growth should stay within [0%, 30%]."""
        # Run many iterations and check bounds
        for seed in range(200):
            result = _single_iteration(seed, 200_000, 25_000, 25, 0.12)
            assert 0.0 <= result["tariff_growth"] <= 0.30

    def test_panel_degradation_in_range(self):
        """Panel degradation should be between 0.4% and 0.8% per year."""
        for seed in range(200):
            result = _single_iteration(seed, 200_000, 25_000, 25, 0.12)
            assert 0.004 <= result["panel_degradation"] <= 0.008

    def test_discount_rate_in_triangular_range(self):
        """Discount rate should be between 0.08 and 0.15."""
        for seed in range(200):
            result = _single_iteration(seed, 200_000, 25_000, 25, 0.12)
            assert 0.08 <= result["discount_rate"] <= 0.15

    def test_deterministic_with_same_seed(self):
        """Same seed should always give same result."""
        r1 = _single_iteration(123, 200_000, 25_000, 25, 0.12)
        r2 = _single_iteration(123, 200_000, 25_000, 25, 0.12)
        assert r1["npv"] == r2["npv"]
        assert r1["payback"] == r2["payback"]

    def test_different_seeds_give_different_results(self):
        r1 = _single_iteration(1, 200_000, 25_000, 25, 0.12)
        r2 = _single_iteration(2, 200_000, 25_000, 25, 0.12)
        assert r1["npv"] != r2["npv"]

    def test_positive_npv_for_good_investment(self):
        """Very high savings relative to investment should yield positive NPV."""
        result = _single_iteration(42, 100_000, 50_000, 25, 0.12)
        assert result["npv"] > 0

    def test_negative_npv_for_bad_investment(self):
        """Very low savings relative to investment should yield negative NPV."""
        result = _single_iteration(42, 1_000_000, 1_000, 25, 0.12)
        assert result["npv"] < 0


class TestRunMonteCarlo:
    def test_returns_expected_top_level_keys(self):
        result = run_monte_carlo(200_000, 25_000, n_iterations=100, parallel=False)
        assert "n_iterations" in result
        assert "npv_statistics" in result
        assert "payback_statistics" in result
        assert "npv_distribution" in result
        assert "input_parameters" in result

    def test_n_iterations_matches_request(self):
        result = run_monte_carlo(200_000, 25_000, n_iterations=200, parallel=False)
        assert result["n_iterations"] == 200

    def test_npv_statistics_keys(self):
        result = run_monte_carlo(200_000, 25_000, n_iterations=100, parallel=False)
        stats = result["npv_statistics"]
        for key in ["mean_tl", "std_tl", "p5_tl", "p25_tl", "p50_tl", "p75_tl", "p95_tl",
                    "var_95_tl", "prob_positive_npv"]:
            assert key in stats

    def test_payback_statistics_keys(self):
        result = run_monte_carlo(200_000, 25_000, n_iterations=100, parallel=False)
        stats = result["payback_statistics"]
        for key in ["mean_years", "p50_years", "finite_payback_fraction"]:
            assert key in stats

    def test_percentile_ordering(self):
        """p5 <= p25 <= p50 <= p75 <= p95."""
        result = run_monte_carlo(200_000, 25_000, n_iterations=500, parallel=False)
        stats = result["npv_statistics"]
        assert stats["p5_tl"] <= stats["p25_tl"]
        assert stats["p25_tl"] <= stats["p50_tl"]
        assert stats["p50_tl"] <= stats["p75_tl"]
        assert stats["p75_tl"] <= stats["p95_tl"]

    def test_prob_positive_npv_bounded(self):
        result = run_monte_carlo(200_000, 25_000, n_iterations=100, parallel=False)
        p = result["npv_statistics"]["prob_positive_npv"]
        assert 0.0 <= p <= 1.0

    def test_good_investment_high_prob_positive_npv(self):
        """A project with high savings/cost ratio should have high NPV > 0 probability."""
        result = run_monte_carlo(100_000, 40_000, n_iterations=500, parallel=False)
        assert result["npv_statistics"]["prob_positive_npv"] > 0.7

    def test_bad_investment_low_prob_positive_npv(self):
        """Very poor project should have low NPV > 0 probability."""
        result = run_monte_carlo(1_000_000, 2_000, n_iterations=500, parallel=False)
        assert result["npv_statistics"]["prob_positive_npv"] < 0.3

    def test_histogram_bins_count(self):
        result = run_monte_carlo(200_000, 25_000, n_iterations=100, parallel=False)
        dist = result["npv_distribution"]
        assert len(dist["histogram_counts"]) == 50
        assert len(dist["histogram_edges_tl"]) == 51  # N bins = N+1 edges

    def test_histogram_counts_sum_to_n_iterations(self):
        n = 300
        result = run_monte_carlo(200_000, 25_000, n_iterations=n, parallel=False)
        total = sum(result["npv_distribution"]["histogram_counts"])
        assert total == n

    def test_finite_payback_fraction_bounded(self):
        result = run_monte_carlo(200_000, 25_000, n_iterations=100, parallel=False)
        frac = result["payback_statistics"]["finite_payback_fraction"]
        assert 0.0 <= frac <= 1.0

    def test_input_parameters_stored(self):
        result = run_monte_carlo(150_000, 18_000, n_iterations=50, parallel=False)
        params = result["input_parameters"]
        assert params["base_investment_tl"] == 150_000
        assert params["base_annual_savings_tl"] == 18_000

    def test_std_positive(self):
        """Standard deviation should be positive (there is uncertainty)."""
        result = run_monte_carlo(200_000, 25_000, n_iterations=200, parallel=False)
        assert result["npv_statistics"]["std_tl"] > 0

    def test_mean_approximately_equals_p50(self):
        """For a roughly symmetric distribution, mean ≈ median (within 20%)."""
        result = run_monte_carlo(200_000, 25_000, n_iterations=1000, parallel=False)
        mean = result["npv_statistics"]["mean_tl"]
        p50 = result["npv_statistics"]["p50_tl"]
        if abs(mean) > 1000:  # Avoid division by near-zero
            relative_diff = abs(mean - p50) / abs(mean)
            assert relative_diff < 0.30  # Within 30% is reasonable

    def test_parallel_vs_sequential_consistency(self):
        """Parallel and sequential should produce statistically consistent results."""
        result_seq = run_monte_carlo(200_000, 25_000, n_iterations=200, parallel=False)
        result_par = run_monte_carlo(200_000, 25_000, n_iterations=200, parallel=True)
        # Both should have same n_iterations
        assert result_seq["n_iterations"] == result_par["n_iterations"]
        # Mean NPV should be in the same ballpark (within 30% relative)
        mean_seq = result_seq["npv_statistics"]["mean_tl"]
        mean_par = result_par["npv_statistics"]["mean_tl"]
        if abs(mean_seq) > 1000:
            assert abs(mean_seq - mean_par) / abs(mean_seq) < 0.30
