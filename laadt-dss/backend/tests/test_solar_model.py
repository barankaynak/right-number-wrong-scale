import hashlib
import json

import pytest

from app.simulation.pv import solar_model as sm
from app.simulation.pv.solar_model import irradiance_provenance, simulate_pv_production
from app.simulation.pv.load_profile import generate_load_profile
from app.llm.ollama_orchestrator import CITY_COORDS


def _no_network(*args, **kwargs):
    raise AssertionError("PVGIS ağ çağrısı yapılmamalıydı (önbellek bekleniyordu)")


def test_pv_production_ankara(monkeypatch):
    # Ankara (39.93°N, 32.86°E), 10 kW, 30° eğim, güney cephe — PVGIS TMY önbelleğinden
    monkeypatch.delenv("IRRADIANCE_SOURCE", raising=False)
    production = simulate_pv_production(39.93, 32.86, 10.0, 30.0, 180.0)
    assert len(production) == 8760
    assert 12000 <= production.sum() <= 19000, production.sum()
    assert production.max() <= 10.0 * 1.25


# ── A23: PVGIS TMY önbelleği, sessiz fallback yok, clear-sky yalnız replay ────

@pytest.mark.parametrize("city", sorted(CITY_COORDS))
def test_benchmark_cities_cached_with_realistic_yield(city, monkeypatch):
    """Benchmark şehirleri önbellekte: koşu sırasında ağ çağrısı YOK; özgül verim
    Türkiye için gerçekçi bantta (clear-sky ~2100 kWh/kWp idi)."""
    monkeypatch.delenv("IRRADIANCE_SOURCE", raising=False)
    monkeypatch.setattr(sm.pvlib.iotools, "get_pvgis_tmy", _no_network)
    lat, lon = CITY_COORDS[city]
    yield_kwh_per_kwp = simulate_pv_production(lat, lon, 1.0, 30.0, 180.0).sum()
    assert 1200 <= yield_kwh_per_kwp <= 1900, (city, yield_kwh_per_kwp)
    assert irradiance_provenance(lat, lon)["irradiance_source"] == "pvgis_tmy_cache"


def test_no_silent_fallback_when_pvgis_unavailable(monkeypatch, tmp_path):
    monkeypatch.delenv("IRRADIANCE_SOURCE", raising=False)
    monkeypatch.setattr(sm, "TMY_CACHE_DIR", tmp_path)

    def _down(*args, **kwargs):
        raise ConnectionError("PVGIS erişilemez")

    monkeypatch.setattr(sm.pvlib.iotools, "get_pvgis_tmy", _down)
    with pytest.raises(sm.IrradianceUnavailable):
        simulate_pv_production(10.0, 10.0, 1.0, 30.0, 180.0)


def test_clearsky_replay_reproduces_july_values(monkeypatch):
    """Temmuz korpusu clear-sky ile üretildi (Ankara 5 kW → 10 541 kWh); replay modu
    eski yolu bayt-özdeş korur (2024 aralığı, 25 °C, 2 m/s, ilk 8760 saat)."""
    monkeypatch.setenv("IRRADIANCE_SOURCE", "clearsky")
    production = simulate_pv_production(39.93, 32.86, 5.0, 30.0, 180.0)
    assert len(production) == 8760
    assert round(float(production.sum())) == 10541
    assert irradiance_provenance(39.93, 32.86)["irradiance_source"] == "clearsky"


def test_unknown_irradiance_source_rejected(monkeypatch):
    monkeypatch.setenv("IRRADIANCE_SOURCE", "magic")
    with pytest.raises(ValueError):
        simulate_pv_production(39.93, 32.86, 1.0, 30.0, 180.0)


def test_tmy_cache_manifest_hashes_match():
    manifest = json.loads((sm.TMY_CACHE_DIR / "MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["files"], "boş önbellek manifesti"
    for name, sha in manifest["files"].items():
        assert hashlib.sha256((sm.TMY_CACHE_DIR / name).read_bytes()).hexdigest() == sha, name


def test_provenance_reports_cache_hash(monkeypatch):
    monkeypatch.delenv("IRRADIANCE_SOURCE", raising=False)
    info = irradiance_provenance(39.93, 32.86)
    manifest = json.loads((sm.TMY_CACHE_DIR / "MANIFEST.json").read_text(encoding="utf-8"))
    assert info["tmy_sha256"] in manifest["files"].values()


def test_load_profile():
    annual_cons = 5000.0
    profile = generate_load_profile('residential', annual_cons)

    assert len(profile) == 8760
    # Toplam tüketim beklenen yıllık tüketim ile aynı olmalı
    assert abs(profile.sum() - annual_cons) < 1.0

    profile_com = generate_load_profile('commercial', 20000.0)
    assert len(profile_com) == 8760
    assert abs(profile_com.sum() - 20000.0) < 1.0
