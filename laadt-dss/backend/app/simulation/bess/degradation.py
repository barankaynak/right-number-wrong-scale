"""
Semi-empirical battery aging model.

Kalenderik (calendar) yaşlanma:
    Q_cal_loss = k_cal × exp(-Ea / (R × T)) × t^0.5

Döngüsel (cyclic) yaşlanma:
    Q_cyc_loss = k_cyc × (DoD)^β × N_cycles

References:
- Schmalstieg et al. (2014) calendar aging
- Ecker et al. (2012) cycle aging
- Rainflow counting: ASTM E1049
"""

import numpy as np
from typing import Optional

# Gas constant (J/mol/K)
R_GAS = 8.314

# Chemistry-specific parameters
# k_cal calibrated so that at T_ref (25°C), calendar loss ≈ 2% per year (LFP),
# 3% (NMC), 1.3% (LTO) using normalized Arrhenius: exp(-Ea/R*(1/T - 1/T_ref))
# k_cal = target_annual_loss / sqrt(365 days) ≈ target / 19.1
CHEMISTRY_PARAMS = {
    'LFP': {
        'k_cal': 1.05e-3,        # Calendar aging coefficient (~2%/yr at 25°C)
        'Ea_cal': 24500,         # Activation energy (J/mol)
        'k_cyc': 5.5e-5,         # Cycle aging coefficient
        'beta': 1.2,             # DoD exponent
        'T_ref': 298.15,         # Reference temperature (25°C in K)
        'soc_ref': 0.5,          # Reference SoC for calendar aging
        'lifetime_cycles': 4000, # Typical full cycles to 80% SoH
        'calendar_life_years': 15,
    },
    'NMC': {
        'k_cal': 1.57e-3,        # ~3%/yr at 25°C
        'Ea_cal': 31700,
        'k_cyc': 9.5e-5,
        'beta': 1.4,
        'T_ref': 298.15,
        'soc_ref': 0.5,
        'lifetime_cycles': 2500,
        'calendar_life_years': 12,
    },
    'LTO': {
        'k_cal': 6.8e-4,         # ~1.3%/yr at 25°C
        'Ea_cal': 18000,
        'k_cyc': 2.5e-5,
        'beta': 0.9,
        'T_ref': 298.15,
        'soc_ref': 0.5,
        'lifetime_cycles': 8000,
        'calendar_life_years': 20,
    },
}


def rainflow_count_cycles(soc_series: np.ndarray) -> list:
    """
    Simple rainflow cycle counting algorithm.
    Returns list of (DoD, mean_soc) tuples for each identified cycle.

    Simplified 3-point method (adequate for annual degradation estimates).
    """
    cycles = []
    residuals = []

    for soc in soc_series:
        residuals.append(soc)

        # Try to extract cycles from residuals
        while len(residuals) >= 3:
            a, b, c = residuals[-3], residuals[-2], residuals[-1]

            range_ab = abs(b - a)
            range_bc = abs(c - b)

            if range_ab <= range_bc:
                # Extract half-cycle (a, b)
                dod = range_ab
                mean_soc = (a + b) / 2
                cycles.append((dod, mean_soc))
                residuals.pop(-2)
                residuals.pop(-2)
            else:
                break

    # Count remaining residuals as half cycles
    for i in range(len(residuals) - 1):
        dod = abs(residuals[i + 1] - residuals[i])
        mean_soc = (residuals[i] + residuals[i + 1]) / 2
        cycles.append((dod * 0.5, mean_soc))  # Half cycle weight = 0.5

    return cycles


def calculate_calendar_aging(
    years: float,
    temperature_c: float,
    avg_soc: float,
    chemistry: str = 'LFP'
) -> float:
    """
    Calendar aging capacity loss fraction.

    Q_cal_loss = k_cal × exp(-Ea/R × (1/T - 1/T_ref)) × t^0.5 × soc_stress

    Uses normalized Arrhenius (= 1.0 at T_ref = 25°C) so k_cal is directly
    interpretable as capacity loss per sqrt(day) at reference conditions.
    """
    params = CHEMISTRY_PARAMS.get(chemistry, CHEMISTRY_PARAMS['LFP'])
    T_kelvin = temperature_c + 273.15
    T_ref = params['T_ref']

    # Normalized Arrhenius: equals 1.0 at T_ref, increases with temperature
    arrhenius = np.exp(-params['Ea_cal'] / R_GAS * (1.0 / T_kelvin - 1.0 / T_ref))

    # Time factor (square root law for SEI growth)
    time_days = years * 365
    time_factor = np.sqrt(time_days)

    # SoC stress factor (higher SoC = more stress)
    soc_stress = 1.0 + 0.3 * (avg_soc - params['soc_ref'])
    soc_stress = max(0.5, min(2.0, soc_stress))  # Clip to reasonable range

    cal_loss = params['k_cal'] * arrhenius * time_factor * soc_stress
    return float(np.clip(cal_loss, 0, 1))


def calculate_cyclic_aging(
    cycles: list,
    chemistry: str = 'LFP'
) -> float:
    """
    Cyclic aging capacity loss fraction from rainflow-counted cycles.

    Q_cyc_loss = k_cyc × sum(DoD^β × cycle_weight)
    """
    if not cycles:
        return 0.0

    params = CHEMISTRY_PARAMS.get(chemistry, CHEMISTRY_PARAMS['LFP'])

    total_damage = sum(
        params['k_cyc'] * (dod ** params['beta'])
        for dod, _ in cycles
        if dod > 0.01  # Ignore micro-cycles < 1% DoD
    )

    return float(np.clip(total_damage, 0, 1))


def calculate_annual_degradation(
    soc_series: np.ndarray,
    chemistry: str = 'LFP',
    temperature_c: float = 25.0,
    years: float = 1.0
) -> dict:
    """
    Full annual degradation analysis combining calendar and cyclic aging.

    Parameters:
        soc_series: 8760-length array of hourly SoC values (0-1)
        chemistry: battery chemistry (LFP, NMC, LTO)
        temperature_c: average ambient temperature
        years: number of years simulated

    Returns:
        SoH after given period, degradation breakdown, estimated lifetime
    """
    avg_soc = float(np.mean(soc_series))

    # Calendar aging
    cal_loss = calculate_calendar_aging(years, temperature_c, avg_soc, chemistry)

    # Cyclic aging via rainflow
    cycles = rainflow_count_cycles(soc_series)
    cyc_loss = calculate_cyclic_aging(cycles, chemistry)

    total_loss = cal_loss + cyc_loss
    soh = max(0.0, 1.0 - total_loss)

    # Estimate remaining lifetime (linear extrapolation to 80% SoH)
    if total_loss > 0:
        years_to_eol = years * (0.20 / total_loss)  # 20% = 1 - 0.80 threshold
    else:
        params = CHEMISTRY_PARAMS.get(chemistry, CHEMISTRY_PARAMS['LFP'])
        years_to_eol = float(params['calendar_life_years'])

    # Full equivalent cycles
    full_cycles = sum(dod for dod, _ in cycles) if cycles else 0.0

    # Degradation cost (TL/kWh per year, rough estimate)
    # Assumes ~20,000 TL/kWh replacement cost
    annual_degradation_cost_per_kwh = 20000 * total_loss / years if years > 0 else 0

    return {
        "soh_after_period": round(soh, 4),
        "calendar_aging_loss": round(cal_loss, 4),
        "cyclic_aging_loss": round(cyc_loss, 4),
        "total_capacity_loss": round(total_loss, 4),
        "equivalent_full_cycles": round(full_cycles, 1),
        "estimated_lifetime_years": round(years_to_eol, 1),
        "annual_degradation_cost_tl_per_kwh": round(annual_degradation_cost_per_kwh, 2),
        "average_soc": round(avg_soc, 3),
        "chemistry": chemistry,
    }


def project_soh_curve(
    first_year_soc_series: np.ndarray,
    chemistry: str = 'LFP',
    temperature_c: float = 25.0,
    projection_years: int = 25
) -> list:
    """
    Projects State of Health curve over system lifetime.

    Uses first-year SoC profile as representative of all years.
    Returns list of (year, SoH) tuples.
    """
    soh_curve = [(0, 1.0)]
    cumulative_cyc_loss = 0.0

    # Get annual cyclic loss (same each year, same usage pattern)
    cycles = rainflow_count_cycles(first_year_soc_series)
    annual_cyc_loss = calculate_cyclic_aging(cycles, chemistry)
    avg_soc = float(np.mean(first_year_soc_series))

    for year in range(1, projection_years + 1):
        # Calendar loss is cumulative (sqrt law applied to total years)
        cal_loss = calculate_calendar_aging(year, temperature_c, avg_soc, chemistry)

        # Cyclic loss accumulates linearly per year
        cumulative_cyc_loss = annual_cyc_loss * year

        soh = max(0.0, 1.0 - cal_loss - cumulative_cyc_loss)
        soh_curve.append((year, round(soh, 4)))

        if soh < 0.80:
            break

    return soh_curve
