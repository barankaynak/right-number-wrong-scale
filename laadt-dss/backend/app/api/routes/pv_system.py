"""
PV System API — Görev 3.3d

POST   /api/v1/pv-system/create                  — Sistem oluştur
GET    /api/v1/pv-system/                         — Tüm sistemler
GET    /api/v1/pv-system/{system_id}              — Sistem detayı
PATCH  /api/v1/pv-system/{system_id}/parameter    — Parametre güncelle
POST   /api/v1/pv-system/{system_id}/run          — Simülasyon çalıştır
DELETE /api/v1/pv-system/{system_id}              — Sistemi sil
GET    /api/v1/pv-system/models/panels            — Panel modeli arama
GET    /api/v1/pv-system/models/inverters         — İnverter modeli arama
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.simulation.pv.system_store import pv_system_store, init_pv_system_schema

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/pv-system", tags=["PV System"])

_schema_ready = False


def _ensure_schema() -> None:
    global _schema_ready
    if not _schema_ready:
        init_pv_system_schema()
        _schema_ready = True


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class ArrayIn(BaseModel):
    modules_per_string: int = 10
    strings_per_inverter: int = 2
    tilt_deg: float = 30.0
    azimuth_deg: float = 180.0
    module_model: str = "Canadian_Solar_CS5P_220M"
    tracking: str = "fixed"
    shade_loss_pct: float = 0.0


class LossesIn(BaseModel):
    soiling_pct: float = 2.0
    wiring_pct: float = 1.0
    mismatch_pct: float = 1.0
    availability_pct: float = 1.0


class LocationIn(BaseModel):
    lat: float
    lon: float
    altitude: float = 0.0
    tz: str = "UTC"


class CreatePvSystemIn(BaseModel):
    system_id: str
    location: LocationIn
    arrays: list[ArrayIn]
    inverter_model: str = ""
    losses: Optional[LossesIn] = None
    dc_ac_ratio: float = 1.2


class UpdateParameterIn(BaseModel):
    target: str
    value: Any


class RunSimulationIn(BaseModel):
    weather_source: str = "pvgis_tmy"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/create")
def create_pv_system(body: CreatePvSystemIn):
    _ensure_schema()
    try:
        result = pv_system_store.create(
            system_id=body.system_id,
            location=body.location.model_dump(),
            arrays=[a.model_dump() for a in body.arrays],
            inverter_model=body.inverter_model,
            losses=body.losses.model_dump() if body.losses else None,
            dc_ac_ratio=body.dc_ac_ratio,
        )
        return {**result, "status": "ok"}
    except Exception as e:
        logger.exception("create_pv_system hatası")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/models/panels")
def search_panels(q: str = Query(default="")):
    """pvlib SAM panel modeli arama."""
    _ensure_schema()
    return {"models": pv_system_store.search_panel_models(q)}


@router.get("/models/inverters")
def search_inverters(q: str = Query(default="")):
    """pvlib inverter modeli arama."""
    _ensure_schema()
    return {"models": pv_system_store.search_inverter_models(q)}


@router.get("/")
def list_pv_systems():
    _ensure_schema()
    systems = pv_system_store.list_systems()
    return {"count": len(systems), "systems": systems}


@router.get("/{system_id}")
def get_pv_system(system_id: str):
    _ensure_schema()
    config = pv_system_store.get(system_id)
    if config is None:
        raise HTTPException(status_code=404, detail=f"Sistem bulunamadı: {system_id}")
    return config


@router.patch("/{system_id}/parameter")
def update_pv_parameter(system_id: str, body: UpdateParameterIn):
    _ensure_schema()
    config = pv_system_store.get(system_id)
    if config is None:
        raise HTTPException(status_code=404, detail=f"Sistem bulunamadı: {system_id}")
    try:
        result = pv_system_store.update(system_id, body.target, body.value)
        return {"status": "ok", **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{system_id}/run")
def run_pv_simulation(system_id: str, body: RunSimulationIn):
    _ensure_schema()
    config = pv_system_store.get(system_id)
    if config is None:
        raise HTTPException(status_code=404, detail=f"Sistem bulunamadı: {system_id}")
    try:
        result = pv_system_store.run_simulation(system_id, body.weather_source)
        return result
    except Exception as e:
        logger.exception("run_pv_simulation hatası")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{system_id}")
def delete_pv_system(system_id: str):
    _ensure_schema()
    deleted = pv_system_store.delete(system_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Sistem bulunamadı: {system_id}")
    return {"status": "ok", "system_id": system_id}
