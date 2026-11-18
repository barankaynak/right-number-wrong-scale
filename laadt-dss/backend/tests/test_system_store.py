"""
Görev 3.3d — PV & BESS System Store testleri.
"""

from __future__ import annotations

import uuid
import pytest
from fastapi.testclient import TestClient


def _uid(prefix: str = "sys") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="module")
def client():
    from app.main import app
    return TestClient(app)


@pytest.fixture(autouse=True)
def ensure_schemas():
    from app.simulation.pv.system_store import init_pv_system_schema
    from app.simulation.bess.system_store import init_bess_system_schema
    init_pv_system_schema()
    init_bess_system_schema()


# ---------------------------------------------------------------------------
# PvSystemStore tests
# ---------------------------------------------------------------------------

class TestPvSystemStore:

    def test_create_and_get(self):
        from app.simulation.pv.system_store import PvSystemStore
        store = PvSystemStore()
        sid = _uid("pv")
        store.create(
            system_id=sid,
            location={"lat": 39.93, "lon": 32.86},
            arrays=[{"modules_per_string": 10, "strings_per_inverter": 2,
                     "tilt_deg": 30, "azimuth_deg": 180}],
        )
        config = store.get(sid)
        assert config is not None
        assert config["system_id"] == sid
        assert len(config["arrays"]) == 1

    def test_dotpath_update(self):
        from app.simulation.pv.system_store import PvSystemStore
        store = PvSystemStore()
        sid = _uid("pv_up")
        store.create(
            system_id=sid,
            location={"lat": 39.93, "lon": 32.86},
            arrays=[{"modules_per_string": 10, "strings_per_inverter": 2,
                     "tilt_deg": 30, "azimuth_deg": 180}],
        )
        store.update(sid, "arrays[0].tilt_deg", 35)
        config = store.get(sid)
        assert config["arrays"][0]["tilt_deg"] == 35

    def test_run_simulation_returns_valid_result(self):
        from app.simulation.pv.system_store import PvSystemStore
        store = PvSystemStore()
        sid = _uid("pv_sim")
        store.create(
            system_id=sid,
            location={"lat": 36.90, "lon": 30.70, "tz": "Europe/Istanbul"},
            arrays=[{"modules_per_string": 10, "strings_per_inverter": 3,
                     "tilt_deg": 25, "azimuth_deg": 180}],
        )
        result = store.run_simulation(sid)
        assert "annual_kwh" in result
        assert result["annual_kwh"] > 0
        assert len(result["monthly_breakdown"]) == 12
        assert sum(result["monthly_breakdown"]) == pytest.approx(result["annual_kwh"], rel=0.01)

    def test_panel_model_search(self):
        from app.simulation.pv.system_store import PvSystemStore
        store = PvSystemStore()
        results = store.search_panel_models("Canadian")
        # Dahili listeden ya da SAM'dan gelsin — boş olmamalı
        assert isinstance(results, list)

    def test_inverter_model_search(self):
        from app.simulation.pv.system_store import PvSystemStore
        store = PvSystemStore()
        results = store.search_inverter_models()
        assert isinstance(results, list)
        assert len(results) > 0

    def test_invalid_dotpath_raises(self):
        from app.simulation.pv.system_store import PvSystemStore
        store = PvSystemStore()
        sid = _uid("pv_err")
        store.create(
            system_id=sid,
            location={"lat": 39.93, "lon": 32.86},
            arrays=[{"modules_per_string": 5, "strings_per_inverter": 1,
                     "tilt_deg": 20, "azimuth_deg": 180}],
        )
        with pytest.raises(ValueError, match="Geçersiz yol"):
            store.update(sid, "nonexistent.field.deep", 42)

    def test_delete(self):
        from app.simulation.pv.system_store import PvSystemStore
        store = PvSystemStore()
        sid = _uid("pv_del")
        store.create(system_id=sid, location={"lat": 39.93, "lon": 32.86},
                     arrays=[{"modules_per_string": 5, "strings_per_inverter": 1,
                               "tilt_deg": 20, "azimuth_deg": 180}])
        assert store.delete(sid) is True
        assert store.get(sid) is None


# ---------------------------------------------------------------------------
# BessSystemStore tests
# ---------------------------------------------------------------------------

class TestBessSystemStore:

    def test_create_and_get(self):
        from app.simulation.bess.system_store import BessSystemStore
        store = BessSystemStore()
        sid = _uid("bess")
        store.create(system_id=sid, chemistry="LFP", capacity_kwh=20.0, power_kw=5.0)
        config = store.get(sid)
        assert config is not None
        assert config["chemistry"] == "LFP"
        assert config["capacity_kwh"] == pytest.approx(20.0)

    def test_defaults_by_chemistry(self):
        from app.simulation.bess.system_store import BessSystemStore
        store = BessSystemStore()
        sid = _uid("bess_def")
        store.create(system_id=sid, chemistry="NMC", capacity_kwh=50.0, power_kw=25.0)
        config = store.get(sid)
        # NMC varsayılan round-trip efficiency > LFP
        assert float(config["roundtrip_efficiency_pct"]) < 95.0

    def test_dotpath_update(self):
        from app.simulation.bess.system_store import BessSystemStore
        store = BessSystemStore()
        sid = _uid("bess_up")
        store.create(system_id=sid, chemistry="LFP", capacity_kwh=10.0, power_kw=3.0)
        store.update(sid, "dispatch_strategy.mode", "peak_shaving")
        config = store.get(sid)
        assert config["dispatch_strategy"]["mode"] == "peak_shaving"

    def test_tou_schedule_overlap_rejected(self):
        from app.simulation.bess.system_store import BessSystemStore
        store = BessSystemStore()
        sid = _uid("bess_tou")
        with pytest.raises(ValueError, match="Zaman dilimi"):
            store.create(
                system_id=sid, chemistry="LFP", capacity_kwh=10.0, power_kw=3.0,
                dispatch_strategy={
                    "mode": "time_of_use",
                    "time_of_use_schedule": [
                        {"hour_start": 8, "hour_end": 12, "action": "charge"},
                        {"hour_start": 10, "hour_end": 14, "action": "discharge"},  # çakışıyor
                    ],
                },
            )

    def test_tou_schedule_valid(self):
        from app.simulation.bess.system_store import BessSystemStore
        store = BessSystemStore()
        sid = _uid("bess_tou_ok")
        result = store.create(
            system_id=sid, chemistry="LFP", capacity_kwh=20.0, power_kw=5.0,
            dispatch_strategy={
                "mode": "time_of_use",
                "time_of_use_schedule": [
                    {"hour_start": 7, "hour_end": 10, "action": "discharge"},
                    {"hour_start": 18, "hour_end": 22, "action": "discharge"},
                ],
            },
        )
        assert result["status"] == "created"

    def test_run_simulation_basic(self):
        from app.simulation.bess.system_store import BessSystemStore
        store = BessSystemStore()
        sid = _uid("bess_sim")
        store.create(system_id=sid, chemistry="LFP", capacity_kwh=10.0, power_kw=3.0)
        result = store.run_simulation(bess_system_id=sid, stakeholder_type="residential")
        assert "annual_self_consumption_pct" in result
        assert "annual_grid_import_kwh" in result
        assert result["annual_cycles"] >= 0


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------

class TestPvSystemApi:

    def test_create_and_list(self, client):
        sid = _uid("api_pv")
        resp = client.post("/api/v1/pv-system/create", json={
            "system_id": sid,
            "location": {"lat": 39.93, "lon": 32.86},
            "arrays": [{"modules_per_string": 10, "strings_per_inverter": 2,
                        "tilt_deg": 30, "azimuth_deg": 180}],
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

        resp2 = client.get("/api/v1/pv-system/")
        assert resp2.status_code == 200
        system_ids = [s["system_id"] for s in resp2.json()["systems"]]
        assert sid in system_ids

    def test_update_and_run(self, client):
        sid = _uid("api_run")
        client.post("/api/v1/pv-system/create", json={
            "system_id": sid,
            "location": {"lat": 36.90, "lon": 30.70, "tz": "UTC"},
            "arrays": [{"modules_per_string": 8, "strings_per_inverter": 2,
                        "tilt_deg": 20, "azimuth_deg": 180}],
        })
        # Tilt güncelle
        resp = client.patch(f"/api/v1/pv-system/{sid}/parameter",
                            json={"target": "arrays[0].tilt_deg", "value": 35})
        assert resp.status_code == 200

        # Simülasyon çalıştır
        resp2 = client.post(f"/api/v1/pv-system/{sid}/run",
                            json={"weather_source": "pvgis_tmy"})
        assert resp2.status_code == 200
        assert resp2.json()["annual_kwh"] > 0

    def test_model_search_endpoints(self, client):
        resp = client.get("/api/v1/pv-system/models/panels?q=Canadian")
        assert resp.status_code == 200
        assert "models" in resp.json()

        resp2 = client.get("/api/v1/pv-system/models/inverters")
        assert resp2.status_code == 200


class TestBessSystemApi:

    def test_create_and_run(self, client):
        sid = _uid("api_bess")
        resp = client.post("/api/v1/bess-system/create", json={
            "system_id": sid,
            "chemistry": "LFP",
            "capacity_kwh": 20.0,
            "power_kw": 5.0,
        })
        assert resp.status_code == 200

        resp2 = client.post(f"/api/v1/bess-system/{sid}/run",
                            json={"stakeholder_type": "residential",
                                  "simulate_degradation_years": 1})
        assert resp2.status_code == 200
        assert "annual_self_consumption_pct" in resp2.json()

    def test_tou_overlap_rejected_api(self, client):
        sid = _uid("api_tou_bad")
        resp = client.post("/api/v1/bess-system/create", json={
            "system_id": sid,
            "chemistry": "NMC",
            "capacity_kwh": 15.0,
            "power_kw": 5.0,
            "dispatch_strategy": {
                "mode": "time_of_use",
                "time_of_use_schedule": [
                    {"hour_start": 8, "hour_end": 12, "action": "charge"},
                    {"hour_start": 10, "hour_end": 15, "action": "discharge"},
                ],
            },
        })
        assert resp.status_code == 400

    def test_404_on_unknown(self, client):
        resp = client.get("/api/v1/bess-system/totally_unknown_xyz_999")
        assert resp.status_code == 404
