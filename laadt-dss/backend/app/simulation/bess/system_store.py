"""
BessSystemStore — BESS sistem konfigürasyonlarını PostgreSQL'de saklar.

Görev 3.3d kapsamında yazılmıştır.

Tablo: bess_systems
  id          SERIAL PRIMARY KEY
  system_id   TEXT UNIQUE NOT NULL
  config      JSONB NOT NULL
  created_at  TIMESTAMPTZ
  updated_at  TIMESTAMPTZ
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

import numpy as np
from sqlalchemy import text

from app.core.database import engine
from app.simulation.bess.battery_model import BatteryModel
from app.simulation.bess.degradation import project_soh_curve
from app.simulation.pv.load_profile import generate_load_profile

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_DDL = """
CREATE TABLE IF NOT EXISTS bess_systems (
    id          SERIAL PRIMARY KEY,
    system_id   TEXT UNIQUE NOT NULL,
    config      JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""
_INDEX_DDL = """
CREATE INDEX IF NOT EXISTS idx_bess_systems_system_id ON bess_systems (system_id);
"""

# Kimyaya göre varsayılan parametreler
_CHEMISTRY_DEFAULTS = {
    "LFP": {"round_trip_efficiency": 0.94, "soc_min": 0.10, "soc_max": 0.90,
             "c_rate_charge": 0.5, "c_rate_discharge": 0.5},
    "NMC": {"round_trip_efficiency": 0.92, "soc_min": 0.10, "soc_max": 0.95,
             "c_rate_charge": 1.0, "c_rate_discharge": 1.0},
    "LTO": {"round_trip_efficiency": 0.97, "soc_min": 0.05, "soc_max": 0.95,
             "c_rate_charge": 3.0, "c_rate_discharge": 3.0},
}


def init_bess_system_schema() -> None:
    with engine.begin() as conn:
        conn.execute(text(_DDL))
    with engine.begin() as conn:
        conn.execute(text(_INDEX_DDL))


# ---------------------------------------------------------------------------
# Nokta-notasyon yardımcısı (aynı PvSystemStore'dan)
# ---------------------------------------------------------------------------

def _apply_dotpath(obj: Any, path: str, value: Any) -> Any:
    parts = re.split(r"\.", path)
    target = obj
    for part in parts[:-1]:
        m = re.match(r"^(\w+)\[(\d+)\]$", part)
        if m:
            target = target[m.group(1)][int(m.group(2))]
        else:
            target = target[part]
    last = parts[-1]
    m = re.match(r"^(\w+)\[(\d+)\]$", last)
    if m:
        target[m.group(1)][int(m.group(2))] = value
    else:
        target[last] = value
    return obj


# ---------------------------------------------------------------------------
# Zaman dilimi çakışma kontrolü
# ---------------------------------------------------------------------------

def _validate_tou_schedule(schedule: list[dict]) -> list[str]:
    """Zaman dilimi kısıtlarının çakışmadığını kontrol eder."""
    errors = []
    intervals: list[tuple[int, int, str]] = []
    for slot in schedule:
        hs = int(slot.get("hour_start", 0))
        he = int(slot.get("hour_end", 1))
        action = slot.get("action", "free")
        if hs < 0 or he > 24 or hs >= he:
            errors.append(f"Geçersiz saat aralığı: {hs}-{he}")
            continue
        for (es, ee, ea) in intervals:
            if hs < ee and he > es:
                errors.append(f"Zaman dilimi çakışması: {hs}-{he} ({action}) ile {es}-{ee} ({ea})")
        intervals.append((hs, he, action))
    return errors


# ---------------------------------------------------------------------------
# BessSystemStore
# ---------------------------------------------------------------------------

class BessSystemStore:

    def create(
        self,
        system_id: str,
        chemistry: str,
        capacity_kwh: float,
        power_kw: float,
        soc_min_pct: float = 10.0,
        soc_max_pct: float = 90.0,
        soc_initial_pct: float = 50.0,
        c_rate_charge_max: float | None = None,
        c_rate_discharge_max: float | None = None,
        roundtrip_efficiency_pct: float | None = None,
        dispatch_strategy: dict | None = None,
        degradation: dict | None = None,
    ) -> dict:
        """BESS sistemi oluşturur ve kaydeder."""
        chem = chemistry.upper()
        defaults = _CHEMISTRY_DEFAULTS.get(chem, _CHEMISTRY_DEFAULTS["LFP"])

        config = {
            "system_id": system_id,
            "chemistry": chem,
            "capacity_kwh": float(capacity_kwh),
            "power_kw": float(power_kw),
            "soc_min_pct": float(soc_min_pct),
            "soc_max_pct": float(soc_max_pct),
            "soc_initial_pct": float(soc_initial_pct),
            "c_rate_charge_max": c_rate_charge_max or defaults["c_rate_charge"],
            "c_rate_discharge_max": c_rate_discharge_max or defaults["c_rate_discharge"],
            "roundtrip_efficiency_pct": roundtrip_efficiency_pct or defaults["round_trip_efficiency"] * 100,
            "dispatch_strategy": dispatch_strategy or {"mode": "self_consumption"},
            "degradation": degradation or {
                "calendar_aging_enabled": True,
                "cyclic_aging_enabled": True,
                "temperature_c": 25.0,
                "eol_soh_pct": 80.0,
            },
        }

        # Zaman dilimi çakışma kontrolü
        tou = (dispatch_strategy or {}).get("time_of_use_schedule", [])
        errs = _validate_tou_schedule(tou)
        if errs:
            raise ValueError("Zaman dilimi hatası: " + "; ".join(errs))

        self._save(system_id, config)
        return {
            "system_id": system_id,
            "status": "created",
            "chemistry": chem,
            "capacity_kwh": capacity_kwh,
            "power_kw": power_kw,
        }

    def update(self, system_id: str, target: str, value: Any) -> dict:
        """Nokta-notasyonlu yolu çözerek parametreyi günceller."""
        config = self._load(system_id)
        if config is None:
            raise ValueError(f"Sistem bulunamadı: {system_id}")
        try:
            _apply_dotpath(config, target, value)
        except (KeyError, IndexError, TypeError) as e:
            raise ValueError(f"Geçersiz yol '{target}': {e}")

        # Zaman dilimi güncellemesinde çakışma kontrolü
        if "time_of_use_schedule" in target:
            tou = config.get("dispatch_strategy", {}).get("time_of_use_schedule", [])
            errs = _validate_tou_schedule(tou)
            if errs:
                raise ValueError("Zaman dilimi hatası: " + "; ".join(errs))

        self._save(system_id, config)
        return {"system_id": system_id, "updated_path": target, "new_value": value}

    def run_simulation(
        self,
        bess_system_id: str,
        pv_hourly_kwh: list[float] | None = None,
        stakeholder_type: str = "residential",
        simulate_degradation_years: int = 1,
    ) -> dict:
        """
        8760 saatlik dispatch simülasyonu.
        pv_hourly_kwh: PV üretim profili (None ise sıfır varsayılır)
        """
        config = self._load(bess_system_id)
        if config is None:
            raise ValueError(f"Sistem bulunamadı: {bess_system_id}")

        capacity = float(config["capacity_kwh"])
        power_kw = float(config["power_kw"])
        chem = config["chemistry"]
        eta = float(config["roundtrip_efficiency_pct"]) / 100.0
        soc_min = float(config["soc_min_pct"]) / 100.0
        soc_max = float(config["soc_max_pct"]) / 100.0

        # Yük profili
        load_arr = generate_load_profile(stakeholder_type, annual_consumption_kwh=5000.0)
        load_arr = np.array(load_arr, dtype=float)

        # PV üretimi
        pv_arr = np.array(pv_hourly_kwh, dtype=float) if pv_hourly_kwh else np.zeros(8760)
        pv_arr = pv_arr[:8760]

        # Dispatch modu
        mode = config.get("dispatch_strategy", {}).get("mode", "self_consumption")
        tou = config.get("dispatch_strategy", {}).get("time_of_use_schedule", [])

        battery = BatteryModel(
            capacity_kwh=capacity,
            chemistry=chem,
            round_trip_efficiency=eta,
            min_soc=soc_min,
            max_soc=soc_max,
            max_charge_crate=float(config.get("c_rate_charge_max", 0.5)),
            max_discharge_crate=float(config.get("c_rate_discharge_max", 0.5)),
        )

        if mode == "self_consumption":
            dispatch = battery.dispatch_self_consumption(pv_arr, load_arr)
        else:
            dispatch = battery.dispatch_self_consumption(pv_arr, load_arr)

        soc_profile = dispatch.get("soc_series", [])
        charge_profile = dispatch.get("charge_series", [])
        discharge_profile = dispatch.get("discharge_series", [])
        grid_import = dispatch.get("grid_import_kwh", 0.0)
        grid_export = dispatch.get("grid_export_kwh", 0.0)

        annual_cycles = float(np.asarray(dispatch.get("annual_cycles", 0.0)).sum())
        annual_grid_import = float(np.asarray(grid_import).sum())
        annual_grid_export = float(np.asarray(grid_export).sum())

        load_total = float(load_arr.sum())
        pv_total = float(pv_arr.sum())
        self_consumption_pct = (
            round((pv_total - annual_grid_export) / max(pv_total, 1e-9) * 100, 1)
            if pv_total > 0 else 0.0
        )

        # Degradasyon simülasyonu
        deg_cfg = config.get("degradation", {})
        soh_curve_data = []
        estimated_lifetime = None
        try:
            if simulate_degradation_years > 1:
                soh_curve_data = project_soh_curve(
                    chemistry=chem,
                    annual_cycles=annual_cycles,
                    years=min(simulate_degradation_years, 25),
                    temperature_c=float(deg_cfg.get("temperature_c", 25)),
                )
                eol_soh = float(deg_cfg.get("eol_soh_pct", 80)) / 100.0
                for entry in soh_curve_data:
                    if entry.get("soh_pct", 100) <= eol_soh * 100:
                        estimated_lifetime = entry.get("year")
                        break
        except Exception as e:
            logger.warning("Degradasyon simülasyonu başarısız: %s", e)

        return {
            "system_id": bess_system_id,
            "annual_self_consumption_pct": self_consumption_pct,
            "annual_grid_import_kwh": round(annual_grid_import, 1),
            "annual_grid_export_kwh": round(annual_grid_export, 1),
            "annual_cycles": round(annual_cycles, 1),
            "soc_profile": [round(float(v), 4) for v in (soc_profile[:8760] if soc_profile else [])],
            "charge_profile": [round(float(v), 4) for v in (charge_profile[:8760] if charge_profile else [])],
            "discharge_profile": [round(float(v), 4) for v in (discharge_profile[:8760] if discharge_profile else [])],
            "degradation": {
                "soh_curve": soh_curve_data,
                "estimated_lifetime_years": estimated_lifetime,
            },
        }

    def get(self, system_id: str) -> Optional[dict]:
        return self._load(system_id)

    def list_systems(self) -> list[dict]:
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT system_id, config, created_at FROM bess_systems ORDER BY created_at DESC")
            ).fetchall()
        result = []
        for r in rows:
            cfg = r[1] if isinstance(r[1], dict) else json.loads(r[1])
            result.append({
                "system_id": r[0],
                "chemistry": cfg.get("chemistry"),
                "capacity_kwh": cfg.get("capacity_kwh"),
                "power_kw": cfg.get("power_kw"),
                "created_at": r[2].isoformat() if r[2] else None,
            })
        return result

    def delete(self, system_id: str) -> bool:
        with engine.begin() as conn:
            result = conn.execute(
                text("DELETE FROM bess_systems WHERE system_id = :sid"), {"sid": system_id}
            )
        return result.rowcount > 0

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _load(self, system_id: str) -> Optional[dict]:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT config FROM bess_systems WHERE system_id = :sid"), {"sid": system_id}
            ).fetchone()
        if row is None:
            return None
        return row[0] if isinstance(row[0], dict) else json.loads(row[0])

    def _save(self, system_id: str, config: dict) -> None:
        now = datetime.now(timezone.utc)
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO bess_systems (system_id, config, created_at, updated_at) "
                    "VALUES (:sid, CAST(:cfg AS jsonb), :ca, :ua) "
                    "ON CONFLICT (system_id) DO UPDATE "
                    "  SET config=EXCLUDED.config, updated_at=EXCLUDED.updated_at"
                ),
                {"sid": system_id, "cfg": json.dumps(config), "ca": now, "ua": now},
            )


bess_system_store = BessSystemStore()
