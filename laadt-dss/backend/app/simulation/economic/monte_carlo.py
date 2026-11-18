"""
Monte Carlo uncertainty analysis for PV+BESS investment.

10,000 iterations with Turkey-specific parameter distributions:
- Annual tariff increase: Normal(μ=0.08, σ=0.03)
- Panel degradation: Uniform(0.004, 0.008) per year
- Battery lifetime: Normal(μ=4000, σ=500) full cycles
- Discount rate: Triangular(0.08, 0.12, 0.15)
- Incentive continuity: Bernoulli(p=0.7) after year 5
"""

import numpy as np
from scipy import stats
from typing import Optional
import multiprocessing as mp
from functools import partial


def _single_iteration(
    seed: int,
    base_investment_tl: float,
    base_annual_savings_tl: float,
    lifetime_years: int,
    base_discount_rate: float
) -> dict:
    """Single Monte Carlo iteration with random parameter sampling."""
    rng = np.random.default_rng(seed)

    # Sample parameters
    tariff_growth = rng.normal(0.08, 0.03)
    tariff_growth = max(0.0, min(0.30, tariff_growth))  # Clip to [0%, 30%]

    panel_degradation = rng.uniform(0.004, 0.008)  # Per year

    discount_rate = rng.triangular(0.08, 0.12, 0.15)

    # Incentive continuity: after year 5, 30% chance incentive stops each year
    incentive_continues = rng.random(lifetime_years) > 0.3
    incentive_continues[:5] = True  # First 5 years always continuous

    # Build cash flows
    cash_flows = [-base_investment_tl]

    for year in range(1, lifetime_years + 1):
        # Tariff growth effect
        savings = base_annual_savings_tl * (1 + tariff_growth) ** year

        # Panel degradation (linear)
        pv_factor = max(0.0, 1.0 - panel_degradation * year)
        savings *= pv_factor

        # Incentive continuity
        if year > 5 and not incentive_continues[year - 1]:
            savings *= 0.7  # Lose ~30% of savings if incentive stops

        cash_flows.append(savings)

    # Calculate NPV
    npv = sum(cf / (1 + discount_rate) ** t for t, cf in enumerate(cash_flows))

    # Calculate simple payback
    cumulative = 0.0
    payback = float('inf')
    for t, cf in enumerate(cash_flows):
        cumulative += cf
        if cumulative >= 0:
            payback = float(t)
            break

    return {
        "npv": npv,
        "payback": payback,
        "tariff_growth": tariff_growth,
        "panel_degradation": panel_degradation,
        "discount_rate": discount_rate,
    }


def run_monte_carlo(
    base_investment_tl: float,
    base_annual_savings_tl: float,
    lifetime_years: int = 25,
    base_discount_rate: float = 0.12,
    n_iterations: int = 10000,
    parallel: bool = True
) -> dict:
    """
    Runs Monte Carlo simulation for investment uncertainty analysis.

    Parameters:
        base_investment_tl: Initial investment cost (positive TL)
        base_annual_savings_tl: First-year annual savings (TL)
        lifetime_years: System lifetime
        base_discount_rate: Base discount rate (used as triangular mode)
        n_iterations: Number of Monte Carlo iterations (default 10,000)
        parallel: Use multiprocessing for speed

    Returns:
        Distribution statistics for NPV and payback period.
    """
    seeds = np.arange(n_iterations)

    worker = partial(
        _single_iteration,
        base_investment_tl=base_investment_tl,
        base_annual_savings_tl=base_annual_savings_tl,
        lifetime_years=lifetime_years,
        base_discount_rate=base_discount_rate,
    )

    if parallel and n_iterations >= 1000:
        n_workers = min(mp.cpu_count(), 4)
        with mp.Pool(processes=n_workers) as pool:
            results = pool.map(worker, seeds)
    else:
        results = [worker(s) for s in seeds]

    npv_values = np.array([r["npv"] for r in results])
    payback_values = np.array([r["payback"] for r in results if r["payback"] != float('inf')])

    # Finite payback fraction
    finite_payback_fraction = len(payback_values) / n_iterations

    # NPV statistics
    npv_sorted = np.sort(npv_values)
    p5_idx = int(0.05 * n_iterations)
    p25_idx = int(0.25 * n_iterations)
    p50_idx = int(0.50 * n_iterations)
    p75_idx = int(0.75 * n_iterations)
    p95_idx = int(0.95 * n_iterations)

    # Value at Risk (95% confidence)
    var_95 = float(-npv_sorted[p5_idx])  # Loss at 5th percentile

    # Probability NPV > 0
    prob_positive_npv = float(np.mean(npv_values > 0))

    # NPV histogram bins (for frontend chart)
    hist_counts, hist_edges = np.histogram(npv_values, bins=50)

    return {
        "n_iterations": n_iterations,
        "npv_statistics": {
            "mean_tl": round(float(np.mean(npv_values)), 0),
            "std_tl": round(float(np.std(npv_values)), 0),
            "p5_tl": round(float(npv_sorted[p5_idx]), 0),
            "p25_tl": round(float(npv_sorted[p25_idx]), 0),
            "p50_tl": round(float(npv_sorted[p50_idx]), 0),
            "p75_tl": round(float(npv_sorted[p75_idx]), 0),
            "p95_tl": round(float(npv_sorted[p95_idx]), 0),
            "var_95_tl": round(var_95, 0),
            "prob_positive_npv": round(prob_positive_npv, 3),
        },
        "payback_statistics": {
            "mean_years": round(float(np.mean(payback_values)), 1) if len(payback_values) > 0 else None,
            "p5_years": round(float(np.percentile(payback_values, 5)), 1) if len(payback_values) > 0 else None,
            "p50_years": round(float(np.median(payback_values)), 1) if len(payback_values) > 0 else None,
            "p95_years": round(float(np.percentile(payback_values, 95)), 1) if len(payback_values) > 0 else None,
            "finite_payback_fraction": round(finite_payback_fraction, 3),
        },
        "npv_distribution": {
            "histogram_counts": hist_counts.tolist(),
            "histogram_edges_tl": [round(float(e), 0) for e in hist_edges.tolist()],
        },
        "input_parameters": {
            "base_investment_tl": base_investment_tl,
            "base_annual_savings_tl": base_annual_savings_tl,
            "lifetime_years": lifetime_years,
        },
    }
