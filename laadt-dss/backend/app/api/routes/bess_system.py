"""
BESS System API — Görev 3.3d

POST   /api/v1/bess-system/create                 — Sistem oluştur
GET    /api/v1/bess-system/                        — Tüm sistemler
GET    /api/v1/bess-system/{system_id}             — Sistem detayı
PATCH  /api/v1/bess-system/{system_id}/parameter   — Parametre güncelle
POST   /api/v1/bess-system/{system_id}/run         — Dispatch simülasyonu
DELETE /api/v1/bess-system/{system_id}             — Sistemi sil
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.simulation.bess.system_store import bess_system_store, init_bess_system_schema

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/bess-system", tags=["BESS System"])

_schema_ready = False


def _ensure_schema() -> None:
    global _schema_ready
    if not _schema_ready:
        init_bess_system_schema()
        _schema_ready = True


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class TouSlotIn(BaseModel):
    hour_start: int
    hour_end: int
    action: str  # charge | discharge | idle | free


class DispatchStrategyIn(BaseModel):
    mode: str = "self_consumption"
    peak_shaving_threshold_kw: Optional[float] = None
    time_of_use_schedule: list[TouSlotIn] = []


class DegradationIn(BaseModel):
    calendar_aging_enabled: bool = True
    cyclic_aging_enabled: bool = True
    temperature_c: float = 25.0
    eol_soh_pct: float = 80.0


class CreateBessSystemIn(BaseModel):
    system_id: str
    chemistry: str = "LFP"
    capacity_kwh: float
    power_kw: float
    soc_min_pct: float = 10.0
    soc_max_pct: float = 90.0
    soc_initial_pct: float = 50.0
    c_rate_charge_max: Optional[float] = None
    c_rate_discharge_max: Optional[float] = None
    roundtrip_efficiency_pct: Optional[float] = None
    dispatch_strategy: Optional[DispatchStrategyIn] = None
    degradation: Optional[DegradationIn] = None


class UpdateParameterIn(BaseModel):
    target: str
    value: Any


class RunBessSimulationIn(BaseModel):
    pv_hourly_kwh: Optional[list[float]] = None
    stakeholder_type: str = "residential"
    simulate_degradation_years: int = 1


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/create")
def create_bess_system(body: CreateBessSystemIn):
    _ensure_schema()
    try:
        ds = body.dispatch_strategy
        result = bess_system_store.create(
            system_id=body.system_id,
            chemistry=body.chemistry,
            capacity_kwh=body.capacity_kwh,
            power_kw=body.power_kw,
            soc_min_pct=body.soc_min_pct,
            soc_max_pct=body.soc_max_pct,
            soc_initial_pct=body.soc_initial_pct,
            c_rate_charge_max=body.c_rate_charge_max,
            c_rate_discharge_max=body.c_rate_discharge_max,
            roundtrip_efficiency_pct=body.roundtrip_efficiency_pct,
            dispatch_strategy=ds.model_dump() if ds else None,
            degradation=body.degradation.model_dump() if body.degradation else None,
        )
        return {"status": "ok", **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("create_bess_system hatası")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/")
def list_bess_systems():
    _ensure_schema()
    systems = bess_system_store.list_systems()
    return {"count": len(systems), "systems": systems}


@router.get("/{system_id}")
def get_bess_system(system_id: str):
    _ensure_schema()
    config = bess_system_store.get(system_id)
    if config is None:
        raise HTTPException(status_code=404, detail=f"Sistem bulunamadı: {system_id}")
    return config


@router.patch("/{system_id}/parameter")
def update_bess_parameter(system_id: str, body: UpdateParameterIn):
    _ensure_schema()
    config = bess_system_store.get(system_id)
    if config is None:
        raise HTTPException(status_code=404, detail=f"Sistem bulunamadı: {system_id}")
    try:
        result = bess_system_store.update(system_id, body.target, body.value)
        return {"status": "ok", **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{system_id}/run")
def run_bess_simulation(system_id: str, body: RunBessSimulationIn):
    _ensure_schema()
    config = bess_system_store.get(system_id)
    if config is None:
        raise HTTPException(status_code=404, detail=f"Sistem bulunamadı: {system_id}")
    try:
        result = bess_system_store.run_simulation(
            bess_system_id=system_id,
            pv_hourly_kwh=body.pv_hourly_kwh,
            stakeholder_type=body.stakeholder_type,
            simulate_degradation_years=body.simulate_degradation_years,
        )
        return result
    except Exception as e:
        logger.exception("run_bess_simulation hatası")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{system_id}")
def delete_bess_system(system_id: str):
    _ensure_schema()
    deleted = bess_system_store.delete(system_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Sistem bulunamadı: {system_id}")
    return {"status": "ok", "system_id": system_id}
