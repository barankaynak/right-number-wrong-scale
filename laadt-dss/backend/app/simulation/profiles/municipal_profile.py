"""
Municipal stakeholder load profiles.
Types: street_lighting, water_pump, public_building, combined
"""

import numpy as np


def generate_municipal_profile(
    sub_type: str,
    annual_consumption_kwh: float
) -> np.ndarray:
    """
    Generates 8760-hour municipal load profile.

    sub_type: 'street_lighting', 'water_pump', 'public_building', 'combined'
    """
    profile = np.zeros(8760)

    for day in range(365):
        # Sunset/sunrise based on day of year (Turkey, ~latitude 39°N)
        # Sunrise: 5:30 (winter) to 5:00 (summer), Sunset: 16:30 (winter) to 20:30 (summer)
        sunrise_hour = 5.5 - 1.0 * np.sin(2 * np.pi * (day - 80) / 365)
        sunset_hour = 18.5 + 2.0 * np.sin(2 * np.pi * (day - 172) / 365)

        if sub_type == 'street_lighting':
            hourly = np.zeros(24)
            for h in range(24):
                if h < sunrise_hour or h >= sunset_hour:
                    hourly[h] = 1.0  # Lights on at night
                else:
                    hourly[h] = 0.02  # Minimal daytime (some sensors/controls)

        elif sub_type == 'water_pump':
            # Pumping highest during peak demand hours (morning/evening)
            hourly = np.array([
                0.4, 0.4, 0.4, 0.4, 0.5, 0.8,
                1.2, 1.5, 1.3, 1.0, 0.9, 0.9,
                0.9, 0.9, 1.0, 1.1, 1.3, 1.5,
                1.4, 1.2, 0.9, 0.7, 0.5, 0.4,
            ])
            # Summer: higher demand for irrigation/cooling
            seasonal = 1.0 + 0.4 * np.sin(2 * np.pi * (day - 172) / 365)
            hourly = hourly * seasonal

        elif sub_type == 'public_building':
            # Working hours only (government offices)
            dow = day % 7
            if dow >= 5:  # Weekend
                hourly = np.full(24, 0.10)
            else:  # Weekday
                hourly = np.array([
                    0.10, 0.10, 0.10, 0.10, 0.12, 0.20,
                    0.40, 0.80, 1.20, 1.40, 1.50, 1.40,
                    1.20, 1.40, 1.50, 1.40, 1.10, 0.60,
                    0.30, 0.20, 0.15, 0.12, 0.10, 0.10,
                ])
                seasonal = 1.0 + 0.30 * np.sin(2 * np.pi * (day - 172) / 365)
                hourly = hourly * seasonal

        elif sub_type == 'combined':
            # Weighted average: 40% street lighting, 30% water pump, 30% public building
            sl = np.zeros(24)
            for h in range(24):
                if h < sunrise_hour or h >= sunset_hour:
                    sl[h] = 1.0

            wp = np.array([0.4, 0.4, 0.4, 0.4, 0.5, 0.8, 1.2, 1.5, 1.3, 1.0, 0.9, 0.9,
                           0.9, 0.9, 1.0, 1.1, 1.3, 1.5, 1.4, 1.2, 0.9, 0.7, 0.5, 0.4])
            wp *= 1.0 + 0.4 * np.sin(2 * np.pi * (day - 172) / 365)

            dow = day % 7
            if dow >= 5:
                pb = np.full(24, 0.10)
            else:
                pb = np.array([0.10, 0.10, 0.10, 0.10, 0.12, 0.20, 0.40, 0.80, 1.20, 1.40,
                               1.50, 1.40, 1.20, 1.40, 1.50, 1.40, 1.10, 0.60, 0.30, 0.20,
                               0.15, 0.12, 0.10, 0.10])
                pb *= 1.0 + 0.30 * np.sin(2 * np.pi * (day - 172) / 365)

            hourly = 0.4 * sl + 0.3 * wp + 0.3 * pb

        else:
            hourly = np.ones(24)

        profile[day * 24:(day + 1) * 24] = hourly

    # Normalize to annual consumption
    if profile.sum() > 0:
        profile = profile / profile.sum() * annual_consumption_kwh

    return profile
