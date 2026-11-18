"""
Commercial stakeholder load profiles.
Types: office, retail, factory, restaurant, hotel
All profiles are 8760-hour normalized to annual_consumption_kwh.
"""

import numpy as np


# Weekday vs weekend distinction for commercial profiles
def _make_annual_profile(
    weekday_hourly: np.ndarray,
    weekend_hourly: np.ndarray,
    seasonal_factor_func=None
) -> np.ndarray:
    """
    Builds 8760-hour profile from weekday/weekend patterns.
    Jan 1, 2024 = Monday. Turkey seasonal: higher summer cooling load.
    """
    assert len(weekday_hourly) == 24
    assert len(weekend_hourly) == 24

    profile = np.zeros(8760)

    # Jan 1, 2024 = Monday (weekday=0)
    for day in range(365):
        dow = day % 7  # 0=Mon, 6=Sun
        is_weekend = dow >= 5  # Sat/Sun

        hourly = weekend_hourly if is_weekend else weekday_hourly

        # Seasonal factor (higher in summer for cooling, Turkey)
        if seasonal_factor_func:
            sf = seasonal_factor_func(day)
        else:
            sf = 1.0 + 0.25 * np.sin(2 * np.pi * (day - 172) / 365)

        profile[day * 24:(day + 1) * 24] = hourly * sf

    return profile


OFFICE_WEEKDAY = np.array([
    0.15, 0.12, 0.12, 0.12, 0.15, 0.25,  # 00-05
    0.50, 0.90, 1.20, 1.40, 1.50, 1.50,  # 06-11
    1.40, 1.50, 1.50, 1.40, 1.20, 0.80,  # 12-17
    0.50, 0.35, 0.25, 0.20, 0.18, 0.15,  # 18-23
])

OFFICE_WEEKEND = np.array([
    0.12, 0.10, 0.10, 0.10, 0.10, 0.12,
    0.15, 0.20, 0.25, 0.30, 0.30, 0.28,
    0.25, 0.25, 0.25, 0.20, 0.18, 0.15,
    0.13, 0.12, 0.12, 0.12, 0.12, 0.12,
])

RETAIL_WEEKDAY = np.array([
    0.10, 0.08, 0.08, 0.08, 0.10, 0.15,
    0.25, 0.60, 1.20, 1.50, 1.60, 1.60,
    1.50, 1.60, 1.60, 1.60, 1.50, 1.20,
    0.80, 0.50, 0.30, 0.20, 0.15, 0.10,
])

RETAIL_WEEKEND = np.array([
    0.10, 0.08, 0.08, 0.08, 0.10, 0.15,
    0.30, 0.80, 1.40, 1.70, 1.80, 1.80,
    1.70, 1.80, 1.80, 1.70, 1.50, 1.20,
    0.80, 0.50, 0.30, 0.20, 0.12, 0.10,
])

FACTORY_WEEKDAY = np.array([
    0.70, 0.70, 0.70, 0.70, 0.75, 0.90,
    1.20, 1.50, 1.60, 1.60, 1.60, 1.50,
    1.30, 1.50, 1.60, 1.60, 1.50, 1.20,
    0.80, 0.75, 0.72, 0.70, 0.70, 0.70,
])

FACTORY_WEEKEND = np.array([
    0.40, 0.40, 0.40, 0.40, 0.40, 0.45,
    0.50, 0.55, 0.60, 0.60, 0.60, 0.60,
    0.55, 0.60, 0.60, 0.58, 0.55, 0.50,
    0.45, 0.42, 0.41, 0.40, 0.40, 0.40,
])


def generate_commercial_profile(
    sub_type: str,
    annual_consumption_kwh: float
) -> np.ndarray:
    """
    Generates 8760-hour commercial load profile.

    sub_type: 'office', 'retail', 'factory', 'restaurant', 'hotel'
    """
    if sub_type == 'office':
        raw = _make_annual_profile(OFFICE_WEEKDAY, OFFICE_WEEKEND)
    elif sub_type == 'retail':
        raw = _make_annual_profile(RETAIL_WEEKDAY, RETAIL_WEEKEND)
    elif sub_type == 'factory':
        raw = _make_annual_profile(
            FACTORY_WEEKDAY, FACTORY_WEEKEND,
            seasonal_factor_func=lambda d: 1.0 + 0.10 * np.sin(2 * np.pi * (d - 172) / 365)
        )
    elif sub_type == 'restaurant':
        # Peak at lunch and dinner
        wd = np.array([
            0.15, 0.12, 0.12, 0.12, 0.15, 0.30,
            0.50, 0.70, 0.80, 0.90, 1.20, 1.50,
            1.60, 1.40, 0.90, 0.80, 1.00, 1.40,
            1.60, 1.50, 1.20, 0.80, 0.50, 0.25,
        ])
        raw = _make_annual_profile(wd, wd)
    elif sub_type == 'hotel':
        # Nearly flat, slight morning and evening peaks
        wd = np.array([
            0.60, 0.55, 0.55, 0.55, 0.60, 0.80,
            1.10, 1.40, 1.30, 1.10, 1.00, 0.95,
            0.95, 0.95, 1.00, 1.05, 1.10, 1.20,
            1.30, 1.30, 1.20, 1.00, 0.85, 0.70,
        ])
        raw = _make_annual_profile(wd, wd)
    else:
        # Generic commercial
        raw = _make_annual_profile(OFFICE_WEEKDAY, OFFICE_WEEKEND)

    raw = raw / raw.sum() * annual_consumption_kwh
    return raw
