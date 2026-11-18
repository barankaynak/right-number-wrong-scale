"""
Inverter REST API adapters.

Each adapter implements the same interface and returns readings in a
standardised format so the rest of the system is vendor-agnostic.

Standard output schema:
    {
        "timestamp":   str  (ISO-8601 UTC),
        "power_w":     float,   # instantaneous AC output (W)
        "daily_kwh":   float,   # energy produced today (kWh)
        "string_data": [        # per-MPPT string details
            {"id": int, "current_a": float, "voltage_v": float, "power_w": float}
        ]
    }

In Phase 3 we have no real inverter hardware, so all adapters generate
plausible simulated data.  The adapter classes are designed so that the
mock implementation can be swapped for a real HTTP call in Phase 4 without
touching any other code.
"""

from __future__ import annotations

import math
import random
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Protocol (interface contract)
# ---------------------------------------------------------------------------

@runtime_checkable
class InverterAdapter(Protocol):
    vendor: str

    def get_current_output(self, system_id: str) -> dict:
        """Return the standard output dict for the given system."""
        ...

    def get_daily_summary(self, system_id: str) -> dict:
        """Return today's energy and performance summary."""
        ...


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _solar_factor(hour: int | None = None) -> float:
    """Return a 0-1 production factor based on the current UTC hour."""
    h = hour if hour is not None else datetime.now(timezone.utc).hour
    if h < 6 or h > 18:
        return 0.0
    return max(0.0, math.sin(math.pi * (h - 6) / 12))


# ---------------------------------------------------------------------------
# SolarEdge adapter (mock)
# ---------------------------------------------------------------------------

class SolarEdgeMockAdapter:
    """Mock SolarEdge REST API (v1/site/{siteId}/currentPowerFlow endpoint)."""

    vendor = "SolarEdge"

    def get_current_output(self, system_id: str) -> dict:
        factor = _solar_factor() * random.uniform(0.90, 1.05)
        # Assume each system_id maps to a ~10 kW site
        peak_w = 10_000
        power_w = peak_w * factor
        strings = [
            {
                "id": i + 1,
                "current_a": round((power_w / 3) / 400, 2),   # ~400 V string
                "voltage_v": round(random.uniform(390, 410), 1),
                "power_w": round(power_w / 3 * random.uniform(0.97, 1.03), 1),
            }
            for i in range(3)
        ]
        return {
            "timestamp": _utc_now(),
            "power_w": round(power_w, 1),
            "daily_kwh": round(power_w * 0.006, 2),  # rough: 6-minute interval
            "string_data": strings,
            "_vendor": self.vendor,
            "_system_id": system_id,
        }

    def get_daily_summary(self, system_id: str) -> dict:
        hour = datetime.now(timezone.utc).hour
        # Integrate sine from 6 to current hour
        produced_kwh = 10 * max(0, (1 - math.cos(math.pi * min(hour - 6, 12) / 12)) / 2 * 0.8)
        return {
            "date": datetime.now(timezone.utc).date().isoformat(),
            "energy_kwh": round(produced_kwh * random.uniform(0.95, 1.05), 2),
            "peak_power_w": round(10_000 * random.uniform(0.93, 1.0), 0),
            "performance_ratio_pct": round(random.uniform(78, 85), 1),
            "_vendor": self.vendor,
            "_system_id": system_id,
        }


# ---------------------------------------------------------------------------
# Huawei FusionSolar adapter (mock)
# ---------------------------------------------------------------------------

class HuaweiFusionSolarMockAdapter:
    """Mock Huawei FusionSolar OpenAPI (/thirdData/getStationRealKpi endpoint)."""

    vendor = "Huawei FusionSolar"

    def get_current_output(self, system_id: str) -> dict:
        factor = _solar_factor() * random.uniform(0.88, 1.04)
        peak_w = 10_000
        power_w = peak_w * factor
        strings = [
            {
                "id": i + 1,
                "current_a": round((power_w / 2) / 380, 2),
                "voltage_v": round(random.uniform(375, 395), 1),
                "power_w": round(power_w / 2 * random.uniform(0.96, 1.04), 1),
            }
            for i in range(2)
        ]
        return {
            "timestamp": _utc_now(),
            "power_w": round(power_w, 1),
            "daily_kwh": round(power_w * 0.006, 2),
            "string_data": strings,
            "_vendor": self.vendor,
            "_system_id": system_id,
        }

    def get_daily_summary(self, system_id: str) -> dict:
        hour = datetime.now(timezone.utc).hour
        produced_kwh = 10 * max(0, (1 - math.cos(math.pi * min(hour - 6, 12) / 12)) / 2 * 0.79)
        return {
            "date": datetime.now(timezone.utc).date().isoformat(),
            "energy_kwh": round(produced_kwh * random.uniform(0.93, 1.05), 2),
            "peak_power_w": round(10_000 * random.uniform(0.90, 0.99), 0),
            "performance_ratio_pct": round(random.uniform(76, 83), 1),
            "_vendor": self.vendor,
            "_system_id": system_id,
        }


# ---------------------------------------------------------------------------
# Fronius Solar.web adapter (mock)
# ---------------------------------------------------------------------------

class FroniusSolarWebMockAdapter:
    """Mock Fronius Solar API (/solar_api/v1/GetPowerFlowRealtimeData.fcgi endpoint)."""

    vendor = "Fronius"

    def get_current_output(self, system_id: str) -> dict:
        factor = _solar_factor() * random.uniform(0.92, 1.03)
        peak_w = 10_000
        power_w = peak_w * factor
        strings = [
            {
                "id": 1,
                "current_a": round(power_w / 380, 2),
                "voltage_v": round(random.uniform(370, 400), 1),
                "power_w": round(power_w * random.uniform(0.98, 1.02), 1),
            }
        ]
        return {
            "timestamp": _utc_now(),
            "power_w": round(power_w, 1),
            "daily_kwh": round(power_w * 0.006, 2),
            "string_data": strings,
            "_vendor": self.vendor,
            "_system_id": system_id,
        }

    def get_daily_summary(self, system_id: str) -> dict:
        hour = datetime.now(timezone.utc).hour
        produced_kwh = 10 * max(0, (1 - math.cos(math.pi * min(hour - 6, 12) / 12)) / 2 * 0.81)
        return {
            "date": datetime.now(timezone.utc).date().isoformat(),
            "energy_kwh": round(produced_kwh * random.uniform(0.94, 1.04), 2),
            "peak_power_w": round(10_000 * random.uniform(0.91, 0.99), 0),
            "performance_ratio_pct": round(random.uniform(79, 86), 1),
            "_vendor": self.vendor,
            "_system_id": system_id,
        }


# ---------------------------------------------------------------------------
# Registry / factory
# ---------------------------------------------------------------------------

_ADAPTERS: dict[str, type] = {
    "solaredge": SolarEdgeMockAdapter,
    "huawei": HuaweiFusionSolarMockAdapter,
    "fronius": FroniusSolarWebMockAdapter,
}


def get_adapter(vendor: str) -> InverterAdapter:
    """
    Return the adapter instance for the given vendor name (case-insensitive).

    Args:
        vendor: One of 'solaredge', 'huawei', 'fronius'.

    Raises:
        ValueError: If the vendor is not supported.
    """
    key = vendor.lower().replace(" ", "")
    adapter_cls = _ADAPTERS.get(key)
    if adapter_cls is None:
        supported = ", ".join(_ADAPTERS.keys())
        raise ValueError(f"Unknown inverter vendor '{vendor}'. Supported: {supported}")
    return adapter_cls()


def list_supported_vendors() -> list[str]:
    """Return all supported vendor identifiers."""
    return list(_ADAPTERS.keys())
