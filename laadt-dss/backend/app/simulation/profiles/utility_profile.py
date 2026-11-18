"""
Distribution utility (dağıtım şirketi) load profiles.
Represents aggregate load at transformer district level.
"""

import numpy as np


def generate_utility_profile(
    n_households: int = 400,
    commercial_pct: float = 20.0,
    industrial_pct: float = 10.0,
    annual_consumption_kwh_per_household: float = 4000.0,
    annual_consumption_kwh: float = None
) -> np.ndarray:
    """
    Generates aggregate 8760-hour load profile for a transformer district.

    Parameters:
        n_households: Number of residential connections
        commercial_pct: Percentage of commercial load relative to residential
        industrial_pct: Percentage of industrial/other load
        annual_consumption_kwh_per_household: Average residential consumption
        annual_consumption_kwh: If provided, overrides n_households calculation

    Returns: 8760-hour aggregate load profile in kWh
    """
    from app.simulation.pv.load_profile import generate_load_profile
    from app.simulation.profiles.commercial_profile import generate_commercial_profile

    # Residential base
    if annual_consumption_kwh is not None:
        # Scale n_households from total consumption
        total_residential_kwh = annual_consumption_kwh / (
            1 + commercial_pct / 100 + industrial_pct / 100
        )
    else:
        total_residential_kwh = n_households * annual_consumption_kwh_per_household

    residential = generate_load_profile('residential', total_residential_kwh)

    # Commercial component
    commercial_kwh = total_residential_kwh * (commercial_pct / 100)
    commercial = generate_commercial_profile('office', commercial_kwh)

    # Industrial/other (factory-like pattern)
    industrial_kwh = total_residential_kwh * (industrial_pct / 100)
    industrial = generate_commercial_profile('factory', industrial_kwh)

    # Aggregate
    total_profile = residential + commercial + industrial

    # Add diversity factor (aggregated load is smoother than individual)
    # Diversity factor ~1.1 for 400+ households (peaks don't coincide perfectly)
    total_profile = total_profile / 1.1

    return total_profile


def get_peak_demand_kw(profile: np.ndarray) -> float:
    """Returns peak demand in kW from hourly profile."""
    return float(np.max(profile))


def get_load_factor(profile: np.ndarray) -> float:
    """Load factor = average load / peak load (0-1)."""
    peak = np.max(profile)
    if peak == 0:
        return 0.0
    return float(np.mean(profile) / peak)
