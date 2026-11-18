"""
Görev 3.3b — Network Builder testleri.
"""

from __future__ import annotations

import uuid
import pytest
from fastapi.testclient import TestClient


def _uid(prefix: str = "net") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="module")
def client():
    from app.main import app
    return TestClient(app)


@pytest.fixture(autouse=True)
def ensure_schema():
    from app.simulation.grid.network_store import init_network_schema
    init_network_schema()


# ---------------------------------------------------------------------------
# NetworkStore unit tests
# ---------------------------------------------------------------------------

class TestNetworkStore:

    def test_create_simple_network(self):
        from app.simulation.grid.network_store import NetworkStore
        ns = NetworkStore()
        nid = _uid()
        result = ns.create(
            network_id=nid,
            buses=[
                {"name": "Bus0", "vn_kv": 0.4, "lat": 39.92, "lon": 32.85},
                {"name": "Bus1", "vn_kv": 0.4, "lat": 39.93, "lon": 32.86},
            ],
            lines=[
                {"from_bus": "Bus0", "to_bus": "Bus1", "length_km": 0.1,
                 "std_type": "NAYY 4x50 SE"}
            ],
            loads=[{"bus": "Bus1", "p_mw": 0.01, "q_mvar": 0.002}],
        )
        assert result["bus_count"] == 2
        assert result["line_count"] == 1
        assert result["load_count"] == 1

    def test_geodata_stored(self):
        from app.simulation.grid.network_store import NetworkStore
        ns = NetworkStore()
        nid = _uid("geo")
        ns.create(
            network_id=nid,
            buses=[{"name": "A", "vn_kv": 0.4, "lat": 41.01, "lon": 28.95}],
        )
        net = ns.get_net(nid)
        assert not net.bus_geodata.empty
        assert net.bus_geodata.at[0, "y"] == pytest.approx(41.01)
        assert net.bus_geodata.at[0, "x"] == pytest.approx(28.95)

    def test_update_element(self):
        from app.simulation.grid.network_store import NetworkStore
        ns = NetworkStore()
        nid = _uid("upd")
        ns.create(
            network_id=nid,
            buses=[
                {"name": "B0", "vn_kv": 0.4, "lat": 39.0, "lon": 32.0},
                {"name": "B1", "vn_kv": 0.4, "lat": 39.1, "lon": 32.1},
            ],
            loads=[{"bus": "B1", "p_mw": 0.01, "q_mvar": 0.002}],
        )
        ns.update_element(nid, "load", 0, "update", {"p_mw": 0.02})
        net = ns.get_net(nid)
        assert net.load.at[0, "p_mw"] == pytest.approx(0.02)

    def test_delete_network(self):
        from app.simulation.grid.network_store import NetworkStore
        ns = NetworkStore()
        nid = _uid("del")
        ns.create(network_id=nid, buses=[{"name": "X", "vn_kv": 0.4}])
        assert ns.delete(nid) is True
        assert ns.get_net(nid) is None

    def test_run_loadflow_converges(self):
        from app.simulation.grid.network_store import NetworkStore
        ns = NetworkStore()
        nid = _uid("lf")
        ns.create(
            network_id=nid,
            buses=[
                {"name": "Slack", "vn_kv": 0.4},
                {"name": "L1", "vn_kv": 0.4},
            ],
            lines=[{"from_bus": "Slack", "to_bus": "L1", "length_km": 0.1}],
            loads=[{"bus": "L1", "p_mw": 0.01, "q_mvar": 0.002}],
        )
        result = ns.run_loadflow(nid)
        assert result["converged"] is True
        assert len(result["buses"]) == 2
        assert "summary" in result

    def test_geojson_valid(self):
        from app.simulation.grid.network_store import NetworkStore
        ns = NetworkStore()
        nid = _uid("gj")
        ns.create(
            network_id=nid,
            buses=[
                {"name": "N1", "vn_kv": 0.4, "lat": 39.92, "lon": 32.85},
                {"name": "N2", "vn_kv": 0.4, "lat": 39.93, "lon": 32.86},
            ],
            lines=[{"from_bus": "N1", "to_bus": "N2", "length_km": 0.1}],
        )
        geojson = ns.get_geojson(nid)
        assert geojson["type"] == "FeatureCollection"
        assert len(geojson["features"]) >= 2  # en az 2 bus Point + hat LineString
        # Her bus bir Point, her hat bir LineString olmalı
        types = {f["geometry"]["type"] for f in geojson["features"]}
        assert "Point" in types
        assert "LineString" in types


# ---------------------------------------------------------------------------
# Network API endpoint tests
# ---------------------------------------------------------------------------

class TestNetworkApi:

    def test_create_and_get(self, client):
        nid = _uid("api")
        resp = client.post("/api/v1/network/create", json={
            "network_id": nid,
            "buses": [
                {"name": "A", "vn_kv": 0.4, "lat": 39.9, "lon": 32.8},
                {"name": "B", "vn_kv": 0.4, "lat": 39.91, "lon": 32.81},
            ],
            "lines": [{"from_bus": "A", "to_bus": "B", "length_km": 0.15}],
            "loads": [{"bus": "B", "p_mw": 0.008}],
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["bus_count"] == 2

        resp2 = client.get(f"/api/v1/network/{nid}")
        assert resp2.status_code == 200
        assert len(resp2.json()["buses"]) == 2

    def test_list_networks(self, client):
        resp = client.get("/api/v1/network/")
        assert resp.status_code == 200
        assert "networks" in resp.json()

    def test_run_loadflow_endpoint(self, client):
        nid = _uid("run")
        client.post("/api/v1/network/create", json={
            "network_id": nid,
            "buses": [{"name": "S", "vn_kv": 0.4}, {"name": "T", "vn_kv": 0.4}],
            "lines": [{"from_bus": "S", "to_bus": "T", "length_km": 0.1}],
            "loads": [{"bus": "T", "p_mw": 0.01}],
        })
        resp = client.post(f"/api/v1/network/{nid}/run", json={"scenario": "peak_load"})
        assert resp.status_code == 200
        assert resp.json()["converged"] is True

    def test_geojson_endpoint(self, client):
        nid = _uid("geoji")
        client.post("/api/v1/network/create", json={
            "network_id": nid,
            "buses": [
                {"name": "P", "vn_kv": 0.4, "lat": 38.42, "lon": 27.14},
                {"name": "Q", "vn_kv": 0.4, "lat": 38.43, "lon": 27.15},
            ],
            "lines": [{"from_bus": "P", "to_bus": "Q", "length_km": 0.1}],
        })
        resp = client.get(f"/api/v1/network/{nid}/geojson")
        assert resp.status_code == 200
        gj = resp.json()
        assert gj["type"] == "FeatureCollection"

    def test_update_element_endpoint(self, client):
        nid = _uid("uel")
        client.post("/api/v1/network/create", json={
            "network_id": nid,
            "buses": [{"name": "U", "vn_kv": 0.4}, {"name": "V", "vn_kv": 0.4}],
            "loads": [{"bus": "V", "p_mw": 0.01}],
        })
        resp = client.put(f"/api/v1/network/{nid}/element", json={
            "element_type": "load",
            "element_id": 0,
            "action": "update",
            "updates": {"p_mw": 0.025},
        })
        assert resp.status_code == 200

    def test_delete_endpoint(self, client):
        nid = _uid("del")
        client.post("/api/v1/network/create", json={
            "network_id": nid,
            "buses": [{"name": "Z", "vn_kv": 0.4}],
        })
        resp = client.delete(f"/api/v1/network/{nid}")
        assert resp.status_code == 200
        resp2 = client.get(f"/api/v1/network/{nid}")
        assert resp2.status_code == 404

    def test_404_for_unknown_network(self, client):
        resp = client.get("/api/v1/network/totally_unknown_xyz_999")
        assert resp.status_code == 404
