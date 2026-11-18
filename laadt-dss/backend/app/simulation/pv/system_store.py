"""
PvSystemStore — GES sistem konfigürasyonlarını PostgreSQL'de saklar.

Görev 3.3d kapsamında yazılmıştır.

Tablo: pv_systems
  id          SERIAL PRIMARY KEY
  system_id   TEXT UNIQUE NOT NULL
  config      JSONB NOT NULL   -- lokasyon, array listesi, inverter, kayıplar
  created_at  TIMESTAMPTZ
  updated_at  TIMESTAMPTZ

Nokta-notasyon güncelleme örneği:
  target = "arrays[0].tilt_deg"  →  config["arrays"][0]["tilt_deg"] = value
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

import numpy as np
import pandas as pd
import pvlib
from pvlib.location import Location
from pvlib.modelchain import ModelChain
from pvlib.pvsystem import PVSystem
from pvlib.temperature import TEMPERATURE_MODEL_PARAMETERS
from sqlalchemy import text

from app.core.database import engine

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_DDL = """
CREATE TABLE IF NOT EXISTS pv_systems (
    id          SERIAL PRIMARY KEY,
    system_id   TEXT UNIQUE NOT NULL,
    config      JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""
_INDEX_DDL = """
CREATE INDEX IF NOT EXISTS idx_pv_systems_system_id ON pv_systems (system_id);
"""

# Dahili panel modeli katalogu (pvlib retrieve_sam fallback)
_BUILTIN_PANELS = [
    "Canadian_Solar_CS5P_220M",
    "Canadian_Solar_CS6K_275M",
    "Jinko_Solar_JKM300M_60",
    "LONGi_Solar_LR4_60HPH_370M",
    "SunPower_SPR_X22_360",
    "Trina_Solar_TSM_400DE15M",
    "Risen_Energy_RSM144_6_395M",
    "Hanwha_Q_CELLS_Q_PEAK_DUO_G6_330",
]

_BUILTIN_INVERTERS = [
    "SMA_Sunny_Boy_3000TL",
    "SMA_Sunny_Tripower_25000TL",
    "Fronius_Symo_10_0_3_208",
    "Huawei_SUN2000_20KTL",
    "ABB_PVI_10_0_I_OUTD_S_US",
]


def init_pv_system_schema() -> None:
    with engine.begin() as conn:
        conn.execute(text(_DDL))
    with engine.begin() as conn:
        conn.execute(text(_INDEX_DDL))


# ---------------------------------------------------------------------------
# Nokta-notasyon yardımcısı
# ---------------------------------------------------------------------------

def _apply_dotpath(obj: Any, path: str, value: Any) -> Any:
    """
    'arrays[0].tilt_deg' gibi nokta-notasyonlu yolu çözerek obj'yi günceller.
    Değiştirilmiş nesneyi döner.
    """
    parts = re.split(r"\.", path)
    target = obj
    for i, part in enumerate(parts[:-1]):
        m = re.match(r"^(\w+)\[(\d+)\]$", part)
        if m:
            key, idx = m.group(1), int(m.group(2))
            target = target[key][idx]
        else:
            target = target[part]
    last = parts[-1]
    m = re.match(r"^(\w+)\[(\d+)\]$", last)
    if m:
        key, idx = m.group(1), int(m.group(2))
        target[key][idx] = value
    else:
        target[last] = value
    return obj


def _get_dotpath(obj: Any, path: str) -> Any:
    parts = re.split(r"\.", path)
    target = obj
    for part in parts:
        m = re.match(r"^(\w+)\[(\d+)\]$", part)
        if m:
            key, idx = m.group(1), int(m.group(2))
            target = target[key][idx]
        else:
            target = target[part]
    return target


# ---------------------------------------------------------------------------
# PvSystemStore
# ---------------------------------------------------------------------------

class PvSystemStore:

    def create(
        self,
        system_id: str,
        location: dict,
        arrays: list[dict],
        inverter_model: str = "",
        losses: dict | None = None,
        dc_ac_ratio: float = 1.2,
    ) -> dict:
        """
        GES sistemi oluşturur ve kaydeder.
        Her array: {modules_per_string, strings_per_inverter, tilt_deg, azimuth_deg,
                    module_model, tracking, shade_loss_pct}
        location: {lat, lon, altitude, tz}
        """
        config = {
            "system_id": system_id,
            "location": location,
            "arrays": arrays,
            "inverter_model": inverter_model,
            "losses": losses or {"soiling_pct": 2.0, "wiring_pct": 1.0,
                                  "mismatch_pct": 1.0, "availability_pct": 1.0},
            "dc_ac_ratio": dc_ac_ratio,
        }
        self._save(system_id, config)
        return {"system_id": system_id, "status": "created", "array_count": len(arrays)}

    def update(self, system_id: str, target: str, value: Any) -> dict:
        """
        Nokta-notasyonlu yolu çözerek belirli parametreyi günceller.
        Örn: target='arrays[0].tilt_deg', value=35
        """
        config = self._load(system_id)
        if config is None:
            raise ValueError(f"Sistem bulunamadı: {system_id}")
        try:
            _apply_dotpath(config, target, value)
        except (KeyError, IndexError, TypeError) as e:
            raise ValueError(f"Geçersiz yol '{target}': {e}")
        self._save(system_id, config)
        return {"system_id": system_id, "updated_path": target, "new_value": value}

    def run_simulation(
        self,
        system_id: str,
        weather_source: str = "pvgis_tmy",
    ) -> dict:
        """
        pvlib ModelChain ile PV üretim simülasyonu çalıştırır.
        Dönüş: annual_kwh, monthly_breakdown[12], capacity_factor_pct,
                performance_ratio, specific_yield, losses_breakdown
        """
        config = self._load(system_id)
        if config is None:
            raise ValueError(f"Sistem bulunamadı: {system_id}")

        loc_cfg = config["location"]
        lat = float(loc_cfg["lat"])
        lon = float(loc_cfg["lon"])
        tz = loc_cfg.get("tz", "UTC")

        location = Location(lat, lon, tz=tz, altitude=float(loc_cfg.get("altitude", 0)))

        # Hava verisi
        try:
            tmy_data, _, _, _ = pvlib.iotools.get_pvgis_tmy(lat, lon, map_variables=True)
        except Exception:
            times = pd.date_range("2024-01-01", periods=8760, freq="h", tz="UTC")
            tmy_data = location.get_clearsky(times)
            tmy_data["temp_air"] = 20.0
            tmy_data["wind_speed"] = 2.0

        # Toplam kurulu güç (kW)
        total_pdc0_w = 0.0
        arrays_cfg = config.get("arrays", [{}])
        for arr in arrays_cfg:
            m_per_s = int(arr.get("modules_per_string", 10))
            s_per_inv = int(arr.get("strings_per_inverter", 2))
            # Standart güç: 330 Wp/panel varsayılan
            total_pdc0_w += m_per_s * s_per_inv * 330.0

        total_pdc0_w = max(total_pdc0_w, 1000.0)

        # İlk arrayin tilt/azimuth değerlerini kullan
        first_arr = arrays_cfg[0] if arrays_cfg else {}
        tilt = float(first_arr.get("tilt_deg", 30))
        azimuth = float(first_arr.get("azimuth_deg", 180))
        tracking = first_arr.get("tracking", "fixed")

        losses = config.get("losses", {})
        loss_factor = 1.0 - (
            float(losses.get("soiling_pct", 2)) +
            float(losses.get("wiring_pct", 1)) +
            float(losses.get("mismatch_pct", 1))
        ) / 100.0

        system = PVSystem(
            surface_tilt=tilt,
            surface_azimuth=azimuth,
            module_parameters={"pdc0": total_pdc0_w, "gamma_pdc": -0.004},
            inverter_parameters={"pdc0": total_pdc0_w, "eta_inv_nom": 0.96},
            temperature_model_parameters=TEMPERATURE_MODEL_PARAMETERS["sapm"]["open_rack_glass_glass"],
        )
        mc = ModelChain(system, location, aoi_model="physical", spectral_model="no_loss")
        mc.run_model(tmy_data)

        ac_kwh = (mc.results.ac / 1000.0).clip(lower=0).fillna(0).values[:8760]
        ac_kwh *= loss_factor

        annual_kwh = float(np.sum(ac_kwh))
        monthly = []
        months = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
        h = 0
        for m_days in months:
            hrs = m_days * 24
            monthly.append(round(float(np.sum(ac_kwh[h: h + hrs])), 2))
            h += hrs

        capacity_kw = total_pdc0_w / 1000.0
        capacity_factor = annual_kwh / (capacity_kw * 8760) * 100

        return {
            "system_id": system_id,
            "annual_kwh": round(annual_kwh, 1),
            "monthly_breakdown": monthly,
            "hourly_profile_kwh": [round(float(v), 4) for v in ac_kwh],
            "capacity_factor_pct": round(capacity_factor, 2),
            "performance_ratio_pct": round(loss_factor * 80, 1),
            "specific_yield_kwh_per_kwp": round(annual_kwh / capacity_kw, 1),
            "installed_kw": round(capacity_kw, 2),
            "losses_breakdown": losses,
        }

    def get(self, system_id: str) -> Optional[dict]:
        return self._load(system_id)

    def list_systems(self) -> list[dict]:
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT system_id, config, created_at FROM pv_systems ORDER BY created_at DESC")
            ).fetchall()
        result = []
        for r in rows:
            cfg = r[1] if isinstance(r[1], dict) else json.loads(r[1])
            result.append({
                "system_id": r[0],
                "array_count": len(cfg.get("arrays", [])),
                "created_at": r[2].isoformat() if r[2] else None,
            })
        return result

    def delete(self, system_id: str) -> bool:
        with engine.begin() as conn:
            result = conn.execute(
                text("DELETE FROM pv_systems WHERE system_id = :sid"), {"sid": system_id}
            )
        return result.rowcount > 0

    def search_panel_models(self, query: str = "") -> list[str]:
        """pvlib SAM veritabanında panel modeli arar; hata durumunda dahili liste döner."""
        try:
            sandia_modules = pvlib.pvsystem.retrieve_sam("SandiaMod")
            all_models = list(sandia_modules.columns)
            if query:
                q = query.lower()
                return [m for m in all_models if q in m.lower()][:20]
            return all_models[:20]
        except Exception:
            if query:
                q = query.lower()
                return [m for m in _BUILTIN_PANELS if q in m.lower()]
            return _BUILTIN_PANELS

    def search_inverter_models(self, query: str = "") -> list[str]:
        try:
            cecinverters = pvlib.pvsystem.retrieve_sam("cecinverter")
            all_models = list(cecinverters.columns)
            if query:
                q = query.lower()
                return [m for m in all_models if q in m.lower()][:20]
            return all_models[:20]
        except Exception:
            if query:
                q = query.lower()
                return [m for m in _BUILTIN_INVERTERS if q in m.lower()]
            return _BUILTIN_INVERTERS

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _load(self, system_id: str) -> Optional[dict]:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT config FROM pv_systems WHERE system_id = :sid"), {"sid": system_id}
            ).fetchone()
        if row is None:
            return None
        return row[0] if isinstance(row[0], dict) else json.loads(row[0])

    def _save(self, system_id: str, config: dict) -> None:
        now = datetime.now(timezone.utc)
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO pv_systems (system_id, config, created_at, updated_at) "
                    "VALUES (:sid, CAST(:cfg AS jsonb), :ca, :ua) "
                    "ON CONFLICT (system_id) DO UPDATE "
                    "  SET config=EXCLUDED.config, updated_at=EXCLUDED.updated_at"
                ),
                {"sid": system_id, "cfg": json.dumps(config), "ca": now, "ua": now},
            )


pv_system_store = PvSystemStore()
