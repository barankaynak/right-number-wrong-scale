"""
Coğrafi (geo) route'ları — bina ayak izi (footprint) servisi.

Frontend 3D harita stüdyosu için bina poligonlarını GeoJSON olarak döndürür.
Veri kaynağı pluggable: settings.FOOTPRINT_PROVIDER ("stub" | "microsoft" | "vida").
"""

from fastapi import APIRouter, HTTPException, Query

from app.geo.footprint_provider import get_provider
from app.core.config import settings

router = APIRouter(prefix="/api/v1/geo", tags=["geo"])


def _provider():
    try:
        name = settings.FOOTPRINT_PROVIDER
        if name == "pmtiles":
            return get_provider("pmtiles", pmtiles_path=settings.PMTILES_PATH)
        return get_provider(name)
    except (NotImplementedError, FileNotFoundError):
        # İstenen sağlayıcı hazır değil / dosya yok → stub'a düş
        return get_provider("stub")


@router.get("/buildings", summary="Bbox içindeki bina ayak izleri (GeoJSON)")
def buildings_in_bbox(
    bbox: str = Query(..., description="minLon,minLat,maxLon,maxLat"),
    limit: int = Query(500, ge=1, le=2000),
):
    try:
        parts = [float(x) for x in bbox.split(",")]
        if len(parts) != 4:
            raise ValueError("bbox 'minLon,minLat,maxLon,maxLat' formatında olmalı")
        min_lon, min_lat, max_lon, max_lat = parts
        return _provider().buildings_in_bbox(min_lon, min_lat, max_lon, max_lat, limit=limit)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/building", summary="Noktadaki bina ayak izi (GeoJSON Feature)")
def building_at_point(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
):
    try:
        feature = _provider().building_at_point(lon, lat)
        if feature is None:
            return {"found": False}
        return feature
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
