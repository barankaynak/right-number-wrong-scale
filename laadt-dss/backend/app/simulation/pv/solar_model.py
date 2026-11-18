"""Saatlik PV üretimi — PVGIS TMY ışınımı + pvlib ModelChain.

A23 (2026-10-14): pvlib 0.15'te `get_pvgis_tmy` iki değer döndürür; eski kod dört değer
açmaya çalıştığı için her çağrı bir `except` ile SESSİZCE clear-sky ışınıma düşüyordu
(Temmuz G1, G4 korpusu ve ilk Ekim denemesi bu yolla üretildi). Şimdi:
  - varsayılan kaynak `pvgis_tmy_cache`: konum başına PVGIS TMY verisi bir kez çekilir ve
    `tmy_cache/` altında saklanır (SHA-256'ları MANIFEST.json'da); sonraki tüm çağrılar
    aynı veriyi okur, benchmark konumlarında koşu sırasında ağ çağrısı olmaz;
  - sessiz fallback YOK: önbellek yoksa ve PVGIS'e ulaşılamazsa `IrradianceUnavailable`;
  - `IRRADIANCE_SOURCE=clearsky` yalnız Temmuz korpusunun yeniden-oynatımı içindir ve eski
    yolu bayt-özdeş korur (2024 aralığı, 25 °C, 2 m/s, ilk 8760 saat).
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pvlib
from pvlib.location import Location
from pvlib.modelchain import ModelChain
from pvlib.pvsystem import PVSystem
from pvlib.temperature import TEMPERATURE_MODEL_PARAMETERS

from app.simulation.compat import july_2026_replay
from app.simulation.loads.turkey_parameters import LOCAL_TIMEZONE

IRRADIANCE_SOURCES = ("pvgis_tmy_cache", "clearsky")
TMY_CACHE_DIR = Path(__file__).resolve().parent / "tmy_cache"


class IrradianceUnavailable(RuntimeError):
    """Işınım verisi alınamadı — sahte veriye düşülmez, hata yükseltilir (A23)."""


def irradiance_source() -> str:
    src = os.environ.get("IRRADIANCE_SOURCE", "pvgis_tmy_cache")
    if src not in IRRADIANCE_SOURCES:
        raise ValueError(f"Bilinmeyen IRRADIANCE_SOURCE: {src!r} (geçerli: {IRRADIANCE_SOURCES})")
    return src


def _cache_name(latitude: float, longitude: float) -> str:
    return f"tmy_{latitude:.2f}_{longitude:.2f}.csv"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _update_manifest(name: str, sha: str) -> None:
    manifest_path = TMY_CACHE_DIR / "MANIFEST.json"
    manifest = (json.loads(manifest_path.read_text(encoding="utf-8"))
                if manifest_path.exists() else {"files": {}})
    manifest["files"][name] = sha
    manifest_path.write_text(json.dumps(manifest, indent=1, sort_keys=True), encoding="utf-8")


def _fetch_and_cache(latitude: float, longitude: float) -> Path:
    TMY_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = TMY_CACHE_DIR / _cache_name(latitude, longitude)
    try:
        data, meta = pvlib.iotools.get_pvgis_tmy(latitude, longitude, map_variables=True)
    except Exception as exc:
        raise IrradianceUnavailable(
            f"PVGIS TMY alınamadı ({latitude:.2f}, {longitude:.2f}): {exc!r}") from exc
    data.to_csv(path)
    path.with_suffix(".json").write_text(json.dumps({
        "latitude": latitude, "longitude": longitude,
        "fetched_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pvlib_version": pvlib.__version__,
        "pvgis_meta": meta,
    }, indent=1, default=str), encoding="utf-8")
    _update_manifest(path.name, _sha256(path))
    return path


def _load_tmy(latitude: float, longitude: float) -> tuple[pd.DataFrame, Path]:
    path = TMY_CACHE_DIR / _cache_name(latitude, longitude)
    if not path.exists():
        path = _fetch_and_cache(latitude, longitude)
    data = pd.read_csv(path, index_col=0)
    data.index = pd.to_datetime(data.index, utc=True)
    return data, path


def _clearsky_weather(location: Location) -> pd.DataFrame:
    # Temmuz yolu (yalnız replay): bayt-özdeş — 2024 artık yılı, sabit 25 °C ve 2 m/s
    times = pd.date_range(start='2024-01-01', end='2024-12-31 23:00:00', freq='h', tz='UTC')
    weather = location.get_clearsky(times)
    weather['temp_air'] = 25
    weather['wind_speed'] = 2
    return weather


def irradiance_provenance(latitude: float, longitude: float) -> dict:
    """PV sonucuna eklenecek veri-kaynağı alanları (sayısal değil → provenance grafı
    bunları kayıt olarak almaz; guard değişmez)."""
    src = irradiance_source()
    if src == "clearsky":
        return {"irradiance_source": "clearsky", "tmy_sha256": None}
    _, path = _load_tmy(latitude, longitude)
    return {"irradiance_source": "pvgis_tmy_cache", "tmy_sha256": _sha256(path)}


def simulate_pv_production(
    latitude: float,
    longitude: float,
    panel_kw: float,
    tilt: float,
    azimuth: float,
    surface_type: str = 'open_rack_glass_glass'
):
    """Simulates hourly PV production for a given location and system parameters.
    Returns: 8760 hourly production values in kWh."""
    location = Location(latitude, longitude, tz='UTC')
    if irradiance_source() == "clearsky":
        weather = _clearsky_weather(location)
    else:
        weather, _ = _load_tmy(latitude, longitude)

    system = PVSystem(
        surface_tilt=tilt,
        surface_azimuth=azimuth,
        module_parameters={'pdc0': panel_kw * 1000, 'gamma_pdc': -0.004},  # W
        inverter_parameters={'pdc0': panel_kw * 1000, 'eta_inv_nom': 0.96},  # W
        temperature_model_parameters=TEMPERATURE_MODEL_PARAMETERS['sapm'][surface_type]
    )

    mc = ModelChain(system, location, aoi_model='physical', spectral_model='no_loss')

    mc.run_model(weather)

    # Convert AC output from Watts to kWh
    ac_power_kwh = mc.results.ac / 1000.0

    ac_power_kwh = ac_power_kwh.clip(lower=0)
    ac_power_kwh = ac_power_kwh.fillna(0)

    # Return as numpy array of 8760 length
    values = ac_power_kwh.values[:8760]
    if july_2026_replay():
        return values      # Temmuz-replay: eski UTC-konum eşlemesi korunur (A27)
    # A27: TMY saatleri UTC, yük profilleri yerel saat → PV yerel saate kaydırılır
    # (Türkiye'de yıl boyu sabit ofset; yaz saati yok)
    offset_h = int(pd.Timestamp("2023-01-01", tz=LOCAL_TIMEZONE).utcoffset().total_seconds() // 3600)
    return np.roll(values, offset_h)
