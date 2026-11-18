"""
Network Builder API — Görev 3.3b

POST   /api/v1/network/create                 — Yeni ağ oluştur
GET    /api/v1/network/                        — Tüm ağları listele
GET    /api/v1/network/{network_id}            — Ağ detayı
PUT    /api/v1/network/{network_id}/element    — Eleman güncelle / sil
DELETE /api/v1/network/{network_id}            — Ağı sil
POST   /api/v1/network/{network_id}/run        — Yük akışı çalıştır
GET    /api/v1/network/{network_id}/geojson    — GeoJSON topoloji
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.simulation.grid.network_store import network_store, init_network_schema

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/network", tags=["Network Builder"])

_schema_ready = False


def _ensure_schema() -> None:
    global _schema_ready
    if not _schema_ready:
        init_network_schema()
        _schema_ready = True


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class BusIn(BaseModel):
    name: str
    vn_kv: float = 0.4
    lat: Optional[float] = None
    lon: Optional[float] = None


class LineIn(BaseModel):
    from_bus: str
    to_bus: str
    length_km: float = 0.1
    std_type: str = ""
    name: str = ""
    r_ohm_per_km: float = 0.641
    x_ohm_per_km: float = 0.083
    c_nf_per_km: float = 210.0
    max_i_ka: float = 0.141


class TransformerIn(BaseModel):
    hv_bus: str
    lv_bus: str
    sn_mva: float = 0.4
    std_type: str = ""
    name: str = ""
    vn_hv_kv: float = 20.0
    vn_lv_kv: float = 0.4
    vkr_percent: float = 1.325
    vk_percent: float = 4.0
    pfe_kw: float = 1.35
    i0_percent: float = 0.3413


class LoadIn(BaseModel):
    bus: str
    p_mw: float = 0.01
    q_mvar: float = 0.002
    name: str = ""


class GeneratorIn(BaseModel):
    bus: str
    p_mw: float = 0.01
    type: str = "pv"   # pv | bess | grid_connection
    name: str = ""


class CreateNetworkIn(BaseModel):
    network_id: str
    name: str = ""
    buses: list[BusIn]
    lines: list[LineIn] = []
    transformers: list[TransformerIn] = []
    loads: list[LoadIn] = []
    generators: list[GeneratorIn] = []


class UpdateElementIn(BaseModel):
    element_type: str   # bus | line | trafo | load | generator
    element_id: int
    action: str         # update | delete
    updates: Optional[dict[str, Any]] = None


class RunLoadflowIn(BaseModel):
    scenario: str = "peak_load"   # peak_load | min_load | max_pv | custom


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/create")
def create_network(body: CreateNetworkIn):
    """Kullanıcı tanımlı pandapower ağı oluşturur ve kaydeder."""
    _ensure_schema()
    try:
        result = network_store.create(
            network_id=body.network_id,
            name=body.name,
            buses=[b.model_dump() for b in body.buses],
            lines=[l.model_dump() for l in body.lines],
            transformers=[t.model_dump() for t in body.transformers],
            loads=[l.model_dump() for l in body.loads],
            generators=[g.model_dump() for g in body.generators],
        )
        return {"status": "ok", **result}
    except Exception as e:
        logger.exception("create_network hatası")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/")
def list_networks():
    """Tüm kayıtlı ağları listeler."""
    _ensure_schema()
    networks = network_store.list_networks()
    return {"count": len(networks), "networks": networks}


@router.get("/{network_id}")
def get_network(network_id: str):
    """Ağ detayını döner (bus/hat/trafo listesi + koordinatlar)."""
    _ensure_schema()
    net = network_store.get_net(network_id)
    if net is None:
        raise HTTPException(status_code=404, detail=f"Ağ bulunamadı: {network_id}")

    buses = [
        {
            "id": int(idx),
            "name": str(row.get("name", "")),
            "vn_kv": float(row.get("vn_kv", 0.4)),
            "lon": float(net.bus_geodata.at[idx, "x"]) if idx in net.bus_geodata.index else None,
            "lat": float(net.bus_geodata.at[idx, "y"]) if idx in net.bus_geodata.index else None,
        }
        for idx, row in net.bus.iterrows()
    ]
    lines = [
        {
            "id": int(idx),
            "name": str(row.get("name", "")),
            "from_bus": int(row.from_bus),
            "to_bus": int(row.to_bus),
            "length_km": float(row.get("length_km", 0)),
        }
        for idx, row in net.line.iterrows()
    ]
    trafos = [
        {
            "id": int(idx),
            "name": str(row.get("name", "")),
            "hv_bus": int(row.hv_bus),
            "lv_bus": int(row.lv_bus),
            "sn_mva": float(row.get("sn_mva", 0.4)),
        }
        for idx, row in net.trafo.iterrows()
    ]
    loads = [
        {
            "id": int(idx),
            "bus": int(row.bus),
            "p_mw": float(row.p_mw),
            "q_mvar": float(row.q_mvar),
            "name": str(row.get("name", "")),
        }
        for idx, row in net.load.iterrows()
    ]
    generators = [
        {
            "id": int(idx),
            "bus": int(row.bus),
            "p_mw": float(row.p_mw),
            "type": str(row.get("type", "pv")),
            "name": str(row.get("name", "")),
        }
        for idx, row in net.sgen.iterrows()
    ]

    return {
        "network_id": network_id,
        "buses": buses,
        "lines": lines,
        "trafos": trafos,
        "loads": loads,
        "generators": generators,
    }


@router.put("/{network_id}/element")
def update_element(network_id: str, body: UpdateElementIn):
    """Ağdaki bir elemanı günceller veya siler."""
    _ensure_schema()
    net = network_store.get_net(network_id)
    if net is None:
        raise HTTPException(status_code=404, detail=f"Ağ bulunamadı: {network_id}")
    try:
        result = network_store.update_element(
            network_id, body.element_type, body.element_id,
            body.action, body.updates or {},
        )
        return {"status": "ok", **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("update_element hatası")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{network_id}")
def delete_network(network_id: str):
    """Ağı siler."""
    _ensure_schema()
    deleted = network_store.delete(network_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Ağ bulunamadı: {network_id}")
    return {"status": "ok", "network_id": network_id}


@router.post("/{network_id}/run")
def run_loadflow(network_id: str, body: RunLoadflowIn):
    """Newton-Raphson yük akışı çalıştırır ve harita verisi döner."""
    _ensure_schema()
    net = network_store.get_net(network_id)
    if net is None:
        raise HTTPException(status_code=404, detail=f"Ağ bulunamadı: {network_id}")
    try:
        result = network_store.run_loadflow(network_id, body.scenario)
        return result
    except Exception as e:
        logger.exception("run_loadflow hatası")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{network_id}/geojson")
def get_geojson(network_id: str):
    """GeoJSON formatında ağ topolojisini döner (Leaflet için)."""
    _ensure_schema()
    net = network_store.get_net(network_id)
    if net is None:
        raise HTTPException(status_code=404, detail=f"Ağ bulunamadı: {network_id}")
    try:
        return network_store.get_geojson(network_id)
    except Exception as e:
        logger.exception("get_geojson hatası")
        raise HTTPException(status_code=500, detail=str(e))
