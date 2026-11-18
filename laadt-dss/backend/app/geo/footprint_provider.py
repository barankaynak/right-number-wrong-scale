"""
footprint_provider.py
=====================
Building-footprint polygon provider for LAaDT-DSS.

Currently ships a deterministic STUB provider so the frontend and API
endpoints can integrate immediately. Real data sources (Microsoft Global
Building Footprints / VIDA combined) are wired in via MicrosoftParquetProvider
and VidaParquetProvider once the parquet files are available.

GeoJSON Feature shape emitted
------------------------------
{
  "type": "Feature",
  "geometry": {
    "type": "Polygon",
    "coordinates": [[[lon, lat], [lon, lat], [lon, lat], [lon, lat], [lon, lat]]]
  },
  "properties": {
    "id":        str,       # e.g. "stub_30700_36900"
    "area_m2":   float,     # computed from projected polygon ring
    "height_m":  float,     # estimated (6.0 – 12.0 m)
    "estimated": True       # always True for stub/height; False only when real data available
  }
}
"""

from __future__ import annotations

from math import cos, radians, floor, sqrt
from typing import Optional, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class BuildingFootprintProvider(Protocol):
    """Minimal interface all providers must satisfy."""

    def buildings_in_bbox(
        self,
        min_lon: float,
        min_lat: float,
        max_lon: float,
        max_lat: float,
        limit: int = 500,
    ) -> dict:
        """Return a GeoJSON FeatureCollection of building polygons."""
        ...

    def building_at_point(self, lon: float, lat: float) -> Optional[dict]:
        """Return a single GeoJSON Feature for the building nearest (lon, lat),
        or None if the provider has no data at that location."""
        ...


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _polygon_area_m2(ring_lonlat: list[list[float]], origin_lon: float, origin_lat: float) -> float:
    """Compute the absolute area in m² of a closed lon/lat ring.

    Uses a local equirectangular projection centred at (origin_lon, origin_lat):
        x = (lon - origin_lon) * 111320 * cos(radians(origin_lat))   [metres East]
        y = (lat - origin_lat) * 110540                               [metres North]
    Then applies the shoelace formula.  The ring may be either open or closed
    (duplicate last point is handled).
    """
    # Drop closing duplicate if present
    pts = ring_lonlat[:-1] if ring_lonlat[-1] == ring_lonlat[0] else ring_lonlat
    n = len(pts)
    if n < 3:
        return 0.0

    cos_lat = cos(radians(origin_lat))
    xs = [(p[0] - origin_lon) * 111320.0 * cos_lat for p in pts]
    ys = [(p[1] - origin_lat) * 110540.0 for p in pts]

    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += xs[i] * ys[j]
        area -= xs[j] * ys[i]
    return abs(area) / 2.0


def _rect_ring(center_lon: float, center_lat: float, half_w_m: float, half_h_m: float) -> list[list[float]]:
    """Build a closed rectangular ring [[lon,lat]×5] centred at (center_lon, center_lat).

    half_w_m  — half-width  in metres (East–West)
    half_h_m  — half-height in metres (North–South)
    """
    cos_lat = cos(radians(center_lat))
    dlon = half_w_m / (111320.0 * cos_lat)
    dlat = half_h_m / 110540.0

    sw = [center_lon - dlon, center_lat - dlat]
    se = [center_lon + dlon, center_lat - dlat]
    ne = [center_lon + dlon, center_lat + dlat]
    nw = [center_lon - dlon, center_lat + dlat]
    return [sw, se, ne, nw, sw]  # closed ring


# ---------------------------------------------------------------------------
# Stub provider
# ---------------------------------------------------------------------------

# Grid spacing in metres between building centres
_GRID_SPACING_M = 25.0

# Building half-dimensions in metres (building is 12 m × 14 m → area ≈ 168 m²)
_HALF_W_M = 6.0   # East–West half-width
_HALF_H_M = 7.0   # North–South half-height

# Maximum bbox span in degrees allowed by this provider (ülke ölçeği sorguları engellenir;
# bölge/mahalle görünümleri desteklenir — bina sayısı `limit` ile sınırlanır)
_MAX_BBOX_SPAN_DEG = 1.0

# Height cycle (deterministic, indexed by grid position)
_HEIGHT_CYCLE = [6.0, 8.0, 10.0, 12.0, 9.0, 7.0, 11.0, 6.5]


def _grid_origin(min_lon: float, min_lat: float) -> tuple[float, float]:
    """Return a stable grid origin just outside the south-west corner of the bbox.

    We anchor the grid at rounded-to-5-decimal-place coordinates so the same
    bbox always produces the same grid (deterministic, no random seed needed).
    """
    # Round down to nearest grid step in degrees
    cos_lat = cos(radians(min_lat))
    step_lon = _GRID_SPACING_M / (111320.0 * cos_lat)
    step_lat = _GRID_SPACING_M / 110540.0
    origin_lon = floor(min_lon / step_lon) * step_lon
    origin_lat = floor(min_lat / step_lat) * step_lat
    return origin_lon, origin_lat


class StubBBoxProvider:
    """Synthesises a deterministic rectangular grid of building footprints.

    Useful for UI integration before real parquet data is wired in.
    All positions derive from a fixed grid — no random state, fully
    reproducible for the same (bbox, limit) inputs.
    """

    # ------------------------------------------------------------------
    def buildings_in_bbox(
        self,
        min_lon: float,
        min_lat: float,
        max_lon: float,
        max_lat: float,
        limit: int = 500,
    ) -> dict:
        """Return a GeoJSON FeatureCollection.

        Raises
        ------
        ValueError
            If the bbox spans more than _MAX_BBOX_SPAN_DEG in either axis.
            Callers should ask the user to zoom in.
        """
        span_lon = max_lon - min_lon
        span_lat = max_lat - min_lat
        if span_lon <= 0 or span_lat <= 0:
            return {"type": "FeatureCollection", "features": []}
        if span_lon > _MAX_BBOX_SPAN_DEG or span_lat > _MAX_BBOX_SPAN_DEG:
            raise ValueError(
                f"Bbox too large ({span_lon:.4f}°×{span_lat:.4f}°). "
                f"Maximum allowed span is {_MAX_BBOX_SPAN_DEG}° in each axis — please zoom in."
            )

        mid_lat = (min_lat + max_lat) / 2.0
        cos_lat = cos(radians(mid_lat)) or 1e-6

        # Adaptif ızgara: yakınlaşmada ~25 m (gerçekçi), uzaklaşmada ~`limit` bina bölgeye yayılır.
        span_m_lon = span_lon * 111320.0 * cos_lat
        span_m_lat = span_lat * 110540.0
        aspect = max(span_m_lon, 1e-6) / max(span_m_lat, 1e-6)
        cols = max(1, round(sqrt(max(1, limit) * aspect)))
        rows = max(1, round(sqrt(max(1, limit) / aspect)))
        spacing_lon_m = max(_GRID_SPACING_M, span_m_lon / cols)
        spacing_lat_m = max(_GRID_SPACING_M, span_m_lat / rows)
        step_lon = spacing_lon_m / (111320.0 * cos_lat)
        step_lat = spacing_lat_m / 110540.0

        origin_lon = floor(min_lon / step_lon) * step_lon
        origin_lat = floor(min_lat / step_lat) * step_lat

        features: list[dict] = []
        col = 0
        lon = origin_lon
        while lon <= max_lon:
            row = 0
            lat = origin_lat
            while lat <= max_lat:
                if min_lon <= lon <= max_lon and min_lat <= lat <= max_lat:
                    # Deterministic height based on (col, row) parity
                    height_m = _HEIGHT_CYCLE[(col * 3 + row * 7) % len(_HEIGHT_CYCLE)]

                    ring = _rect_ring(lon, lat, _HALF_W_M, _HALF_H_M)
                    area = _polygon_area_m2(ring, lon, lat)

                    # Encode grid indices into id to keep it globally unique
                    # Use integer micro-degrees to avoid float formatting issues
                    lon_key = int(round(lon * 1e5))
                    lat_key = int(round(lat * 1e5))
                    fid = f"stub_{lon_key}_{lat_key}"

                    feature = {
                        "type": "Feature",
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [ring],
                        },
                        "properties": {
                            "id": fid,
                            "area_m2": round(area, 2),
                            "height_m": height_m,
                            "estimated": True,
                        },
                    }
                    features.append(feature)
                    if len(features) >= limit:
                        break

                lat += step_lat
                row += 1
            else:
                lon += step_lon
                col += 1
                continue
            break  # inner while hit limit

        return {"type": "FeatureCollection", "features": features}

    # ------------------------------------------------------------------
    def building_at_point(self, lon: float, lat: float) -> Optional[dict]:
        """Return a single rectangular footprint centred on the grid point
        nearest to (lon, lat).

        The grid snap ensures the returned polygon is always consistent
        with what buildings_in_bbox would return for a small bbox around
        the same point.
        """
        cos_lat = cos(radians(lat))
        step_lon = _GRID_SPACING_M / (111320.0 * cos_lat)
        step_lat = _GRID_SPACING_M / 110540.0

        # Snap to nearest grid centre
        snap_lon = round(lon / step_lon) * step_lon
        snap_lat = round(lat / step_lat) * step_lat

        col = int(round((snap_lon - floor(snap_lon / step_lon) * step_lon) / step_lon)) % len(_HEIGHT_CYCLE)
        row = int(round((snap_lat - floor(snap_lat / step_lat) * step_lat) / step_lat)) % len(_HEIGHT_CYCLE)
        height_m = _HEIGHT_CYCLE[(col * 3 + row * 7) % len(_HEIGHT_CYCLE)]

        ring = _rect_ring(snap_lon, snap_lat, _HALF_W_M, _HALF_H_M)
        area = _polygon_area_m2(ring, snap_lon, snap_lat)

        lon_key = int(round(snap_lon * 1e5))
        lat_key = int(round(snap_lat * 1e5))
        fid = f"stub_{lon_key}_{lat_key}"

        return {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [ring],
            },
            "properties": {
                "id": fid,
                "area_m2": round(area, 2),
                "height_m": height_m,
                "estimated": True,
            },
        }


# ===========================================================================
# PMTiles provider — real global building footprints
# ===========================================================================
# Reads a PMTiles v3 archive of MVT vector tiles (Google+Microsoft/VIDA
# "google_microsoft_building_footprints", layer 'building_footprints' at z15
# with an authoritative `area_in_meters` field). No height field → estimated.
#
# The archive can be very large (~200 GB) so tiles are read by byte-range
# (random access); only the touched bytes are fetched. Header + root directory
# are cached; leaf directories are cached on demand. Reads are guarded by a
# lock because FastAPI runs sync handlers in a threadpool and a shared file
# object's seek+read is not atomic.

import gzip as _gzip
import os as _os
import threading as _threading
from math import atan, sinh, log, tan, pi, degrees, radians as _radians

_PMT_ZOOM = 15            # buildings live at max zoom 15
_PMT_MAX_TILES = 80       # cap tiles scanned per bbox (stride-sample beyond this)
_PMT_MIN_AREA_M2 = 8.0    # drop sub-8 m² noise polygons from bbox listings
_PMT_LAYER = "building_footprints"


# ---- minimal MVT (protobuf) decoder — zero external deps ------------------

def _mvt_uvarint(b, p):
    r = 0; s = 0
    while True:
        x = b[p]; p += 1
        r |= (x & 0x7F) << s
        if not (x & 0x80):
            return r, p
        s += 7


def _mvt_skip(b, p, wire):
    if wire == 0:
        _, p = _mvt_uvarint(b, p)
    elif wire == 1:
        p += 8
    elif wire == 2:
        ln, p = _mvt_uvarint(b, p); p += ln
    elif wire == 5:
        p += 4
    return p


def _mvt_zz(u):
    return (u >> 1) ^ (-(u & 1))


def _mvt_decode_value(b):
    import struct
    p = 0; n = len(b)
    while p < n:
        key, p = _mvt_uvarint(b, p); field = key >> 3; wire = key & 7
        if field == 1 and wire == 2:
            ln, p = _mvt_uvarint(b, p); return b[p:p + ln].decode("utf-8", "replace")
        if field == 2 and wire == 5:
            return struct.unpack_from("<f", b, p)[0]
        if field == 3 and wire == 1:
            return struct.unpack_from("<d", b, p)[0]
        if field in (4, 5) and wire == 0:
            v, p = _mvt_uvarint(b, p); return v
        if field == 6 and wire == 0:
            v, p = _mvt_uvarint(b, p); return _mvt_zz(v)
        if field == 7 and wire == 0:
            v, p = _mvt_uvarint(b, p); return bool(v)
        p = _mvt_skip(b, p, wire)
    return None


def _mvt_decode_feature(b, keys, values):
    p = 0; n = len(b); tags = []; geom = []
    while p < n:
        key, p = _mvt_uvarint(b, p); field = key >> 3; wire = key & 7
        if field == 1 and wire == 0:
            _, p = _mvt_uvarint(b, p)
        elif field == 2 and wire == 2:
            ln, p = _mvt_uvarint(b, p); end = p + ln
            while p < end:
                t, p = _mvt_uvarint(b, p); tags.append(t)
        elif field == 3 and wire == 0:
            _, p = _mvt_uvarint(b, p)
        elif field == 4 and wire == 2:
            ln, p = _mvt_uvarint(b, p); end = p + ln
            while p < end:
                g, p = _mvt_uvarint(b, p); geom.append(g)
        else:
            p = _mvt_skip(b, p, wire)
    props = {}
    for i in range(0, len(tags) - 1, 2):
        props[keys[tags[i]]] = values[tags[i + 1]]
    return geom, props


def _mvt_decode_rings(cmds):
    """Decode packed geometry commands → list of rings (tile-local int coords)."""
    x = 0; y = 0; rings = []; ring = []; i = 0; n = len(cmds)
    while i < n:
        cmd = cmds[i]; i += 1
        cid = cmd & 0x7; count = cmd >> 3
        if cid == 1:            # MoveTo
            for _ in range(count):
                x += _mvt_zz(cmds[i]); y += _mvt_zz(cmds[i + 1]); i += 2
                if ring:
                    rings.append(ring)
                ring = [(x, y)]
        elif cid == 2:          # LineTo
            for _ in range(count):
                x += _mvt_zz(cmds[i]); y += _mvt_zz(cmds[i + 1]); i += 2
                ring.append((x, y))
        elif cid == 7:          # ClosePath
            if ring:
                rings.append(ring); ring = []
    if ring:
        rings.append(ring)
    return rings


def _mvt_decode_layer(buf):
    p = 0; n = len(buf); name = None; extent = 4096
    feats = []; keys = []; values = []
    while p < n:
        key, p = _mvt_uvarint(buf, p); field = key >> 3; wire = key & 7
        if field == 1 and wire == 2:
            ln, p = _mvt_uvarint(buf, p); name = buf[p:p + ln].decode("utf-8", "replace"); p += ln
        elif field == 2 and wire == 2:
            ln, p = _mvt_uvarint(buf, p); feats.append(bytes(buf[p:p + ln])); p += ln
        elif field == 3 and wire == 2:
            ln, p = _mvt_uvarint(buf, p); keys.append(buf[p:p + ln].decode("utf-8", "replace")); p += ln
        elif field == 4 and wire == 2:
            ln, p = _mvt_uvarint(buf, p); values.append(_mvt_decode_value(buf[p:p + ln])); p += ln
        elif field == 5 and wire == 0:
            extent, p = _mvt_uvarint(buf, p)
        else:
            p = _mvt_skip(buf, p, wire)
    return name, extent, feats, keys, values


def _mvt_decode_tile(data, want_layer):
    p = 0; n = len(data)
    while p < n:
        key, p = _mvt_uvarint(data, p); field = key >> 3; wire = key & 7
        if field == 3 and wire == 2:
            ln, p = _mvt_uvarint(data, p)
            name, extent, feats, keys, values = _mvt_decode_layer(data[p:p + ln]); p += ln
            if name == want_layer:
                return extent, feats, keys, values
        else:
            p = _mvt_skip(data, p, wire)
    return None


# ---- tile <-> lon/lat math ------------------------------------------------

def _lonlat_to_tile(lon, lat, z):
    n = 2 ** z
    x = int((lon + 180.0) / 360.0 * n)
    lat_r = _radians(lat)
    y = int((1.0 - log(tan(lat_r) + 1.0 / __import__("math").cos(lat_r)) / pi) / 2.0 * n)
    return max(0, min(n - 1, x)), max(0, min(n - 1, y))


def _tilexy_to_lonlat(z, tx, ty, px, py, extent):
    n = 2 ** z
    wx = (tx + px / extent) / n
    wy = (ty + py / extent) / n
    lon = wx * 360.0 - 180.0
    lat = degrees(atan(sinh(pi * (1.0 - 2.0 * wy))))
    return [lon, lat]


def _point_in_ring(lon, lat, ring):
    """Ray-casting point-in-polygon on a lon/lat ring."""
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]; xj, yj = ring[j]
        if ((yi > lat) != (yj > lat)) and (lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def _estimate_height_m(area_m2: float) -> float:
    """Documented height ESTIMATE (dataset has no height). Larger urban TR
    footprints loosely correlate with more storeys (~3 m/storey)."""
    if area_m2 < 80:
        return 6.0    # 1–2 kat
    if area_m2 < 150:
        return 9.0    # ~3 kat
    if area_m2 < 400:
        return 14.0   # ~4–5 kat
    return 18.0       # apartman/ticari ~6 kat


# ---- cached PMTiles archive reader ----------------------------------------

_PMT_TILE_CACHE_MAX = 2048   # decompressed tiles kept in-memory (esp. helps remote)


class _PMTilesArchive:
    """Thin cached reader over a PMTiles v3 archive. Source may be a LOCAL file
    path or an HTTP(S) URL (byte-range reads). Header + root dir cached; leaf
    dirs and decompressed tiles cached on demand. Thread-safe.

    Remote reads use a persistent httpx client (keep-alive → one TLS handshake)
    with an explicit User-Agent (Source Cooperative's CDN 403s python-* UAs).
    """

    def __init__(self, source: str):
        from pmtiles.tile import deserialize_header, deserialize_directory
        self._source = source
        self._is_url = source.startswith(("http://", "https://"))
        self._lock = _threading.Lock()
        self._deser_dir = deserialize_directory
        if self._is_url:
            import httpx
            self._client = httpx.Client(
                headers={"User-Agent": "LAaDT-DSS/1.0 (+pmtiles-range-reader)"},
                timeout=httpx.Timeout(30.0, connect=15.0),
                follow_redirects=True,
                limits=httpx.Limits(max_keepalive_connections=8, max_connections=16),
            )
            self._f = None
        else:
            self._client = None
            self._f = open(source, "rb")
        self._h = deserialize_header(self._read(0, 127))
        self._root = deserialize_directory(self._read(self._h["root_offset"], self._h["root_length"]))
        self._leaf: dict = {}
        self._tiles: dict = {}   # (z,x,y) -> decompressed bytes | None (FIFO-capped)

    def _read(self, off: int, length: int) -> bytes:
        """Byte-range read. HTTP reads run lock-free (httpx client is
        thread-safe) with retry+backoff for transient 5xx/timeouts (Source
        Cooperative's CDN 500s under concurrent bursts); local reads guard the
        shared file's seek+read."""
        if not self._is_url:
            with self._lock:
                self._f.seek(off)
                return self._f.read(length)
        import time as _time
        import httpx
        headers = {"Range": f"bytes={off}-{off + length - 1}"}
        last = None
        for attempt in range(4):
            try:
                r = self._client.get(self._source, headers=headers)
            except httpx.TransportError as e:      # connection/timeout → retryable
                last = e
            else:
                if r.status_code < 500:
                    r.raise_for_status()           # 2xx→return; 4xx→raise (permanent)
                    return r.content
                last = f"HTTP {r.status_code}"      # 5xx → retryable
            if attempt < 3:
                _time.sleep(0.25 * (2 ** attempt))  # 0.25 / 0.5 / 1.0 s backoff
        raise RuntimeError(f"PMTiles remote read failed after 4 attempts: {last}")

    def _cache_tile(self, key, data):
        with self._lock:
            if len(self._tiles) >= _PMT_TILE_CACHE_MAX:
                self._tiles.pop(next(iter(self._tiles)))  # evict oldest (FIFO)
            self._tiles[key] = data

    def get_tile(self, z: int, x: int, y: int):
        from pmtiles.tile import find_tile, zxy_to_tileid, Compression
        ck = (z, x, y)
        with self._lock:
            if ck in self._tiles:
                return self._tiles[ck]
        tid = zxy_to_tileid(z, x, y)
        entries = self._root
        data = None
        for _ in range(4):  # root + up to 3 leaf-directory levels
            e = find_tile(entries, tid)
            if e is None:
                self._cache_tile(ck, None)
                return None
            if e.run_length == 0:  # leaf-directory pointer
                off = self._h["leaf_directory_offset"] + e.offset
                lk = (off, e.length)
                with self._lock:
                    leaf = self._leaf.get(lk)
                if leaf is None:
                    leaf = self._deser_dir(self._read(off, e.length))  # read outside lock
                    with self._lock:
                        self._leaf[lk] = leaf
                entries = leaf
                continue
            data = self._read(self._h["tile_data_offset"] + e.offset, e.length)
            break
        if data is None:
            self._cache_tile(ck, None)
            return None
        if self._h["tile_compression"] == Compression.GZIP:
            data = _gzip.decompress(data)
        self._cache_tile(ck, data)
        return data


class PMTilesFootprintProvider:
    """Real building footprints from a PMTiles v3 (MVT) archive.

    Uses the authoritative `area_in_meters` property for area_m2; height is
    ESTIMATED (dataset has none) and flagged ``estimated=True``.
    """

    def __init__(self, source: str, zoom: int = _PMT_ZOOM, layer: str = _PMT_LAYER):
        # ``source`` is a local file path OR an http(s):// URL (byte-range reads).
        is_url = source.startswith(("http://", "https://"))
        if not is_url and not _os.path.exists(source):
            raise FileNotFoundError(f"PMTiles file not found: {source}")
        self._source = source
        self._zoom = zoom
        self._layer = layer
        self._archive = _PMTilesArchive(source)  # reads header/root → validates URL too

    # -- internal: yield decoded (ring_lonlat, area, source) for one tile ---
    def _tile_buildings(self, tx: int, ty: int):
        data = self._archive.get_tile(self._zoom, tx, ty)
        if data is None:
            return
        decoded = _mvt_decode_tile(data, self._layer)
        if decoded is None:
            return
        extent, feats, keys, values = decoded
        for fb in feats:
            geom, props = _mvt_decode_feature(fb, keys, values)
            rings = _mvt_decode_rings(geom)
            if not rings:
                continue
            ring_ll = [_tilexy_to_lonlat(self._zoom, tx, ty, px, py, extent) for (px, py) in rings[0]]
            if len(ring_ll) < 3:
                continue
            if ring_ll[0] != ring_ll[-1]:
                ring_ll = ring_ll + [ring_ll[0]]  # close ring for GeoJSON
            yield ring_ll, props.get("area_in_meters"), props.get("bf_source")

    @staticmethod
    def _feature(ring_ll, area, source, estimated_area=False):
        clon = sum(p[0] for p in ring_ll[:-1]) / (len(ring_ll) - 1)
        clat = sum(p[1] for p in ring_ll[:-1]) / (len(ring_ll) - 1)
        if area is None:
            area = _polygon_area_m2(ring_ll, clon, clat)
            estimated_area = True
        fid = f"ms_{int(round(clon * 1e6))}_{int(round(clat * 1e6))}"
        return {
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [ring_ll]},
            "properties": {
                "id": fid,
                "area_m2": round(float(area), 2),
                "height_m": _estimate_height_m(float(area)),
                "estimated": True,          # height always estimated
                "area_estimated": estimated_area,
                "source": source or "unknown",
            },
        }

    def buildings_in_bbox(self, min_lon, min_lat, max_lon, max_lat, limit=500) -> dict:
        span_lon = max_lon - min_lon
        span_lat = max_lat - min_lat
        if span_lon <= 0 or span_lat <= 0:
            return {"type": "FeatureCollection", "features": []}

        x0, y1 = _lonlat_to_tile(min_lon, min_lat, self._zoom)  # min_lat → larger y
        x1, y0 = _lonlat_to_tile(max_lon, max_lat, self._zoom)
        if x1 < x0:
            x0, x1 = x1, x0
        if y1 < y0:
            y0, y1 = y1, y0
        txs = list(range(x0, x1 + 1))
        tys = list(range(y0, y1 + 1))
        n_tiles = len(txs) * len(tys)
        stride = 1
        if n_tiles > _PMT_MAX_TILES:
            from math import ceil, sqrt
            stride = ceil(sqrt(n_tiles / _PMT_MAX_TILES))

        # Tüm seçili tile'ları TARA (NW'den kesme YOK → sol-üst kümelenmesi olmaz).
        # Uzak kaynakta tile okumaları paralel (httpx thread-safe, keep-alive pool).
        coords = [(tx, ty) for ty in tys[::stride] for tx in txs[::stride]]

        def _safe_tile(c):
            try:
                return list(self._tile_buildings(c[0], c[1]))
            except Exception:
                return []  # tek tile hatası tüm bbox'ı düşürmesin (kısmi sonuç yeğdir)

        if getattr(self._archive, "_is_url", False) and len(coords) > 1:
            from concurrent.futures import ThreadPoolExecutor
            # 6 eşzamanlı: source.coop CDN yüksek burst'te 500 veriyor (retry _read'de)
            with ThreadPoolExecutor(max_workers=min(6, len(coords))) as ex:
                per_tile = list(ex.map(_safe_tile, coords))
        else:
            per_tile = [_safe_tile(c) for c in coords]

        # bbox içi + min-alan filtresi ile topla (tile sırası: K→G, B→D → mekânsal sıralı)
        collected = []
        for tile in per_tile:
            for ring_ll, area, source in tile:
                clon = sum(p[0] for p in ring_ll[:-1]) / (len(ring_ll) - 1)
                clat = sum(p[1] for p in ring_ll[:-1]) / (len(ring_ll) - 1)
                if not (min_lon <= clon <= max_lon and min_lat <= clat <= max_lat):
                    continue
                if area is not None and area < _PMT_MIN_AREA_M2:
                    continue
                collected.append((ring_ll, area, source))

        # limit'i aşarsa EŞİT örnekle (mekânsal sıralı listeden eşit aralıklı seçim →
        # tüm bbox'a yayılır, tek köşede toplanmaz)
        if len(collected) > limit:
            step = len(collected) / float(limit)
            collected = [collected[int(i * step)] for i in range(limit)]

        features = [self._feature(*c) for c in collected]
        return {"type": "FeatureCollection", "features": features}

    def building_at_point(self, lon: float, lat: float) -> Optional[dict]:
        tx, ty = _lonlat_to_tile(lon, lat, self._zoom)
        best = None
        best_d = None
        for ring_ll, area, source in self._tile_buildings(tx, ty):
            if _point_in_ring(lon, lat, ring_ll):
                return self._feature(ring_ll, area, source)
            clon = sum(p[0] for p in ring_ll[:-1]) / (len(ring_ll) - 1)
            clat = sum(p[1] for p in ring_ll[:-1]) / (len(ring_ll) - 1)
            d = (clon - lon) ** 2 + (clat - lat) ** 2
            if best_d is None or d < best_d:
                best_d = d
                best = (ring_ll, area, source)
        if best is None:
            return None
        return self._feature(*best)


# ---------------------------------------------------------------------------
# Placeholder providers (legacy parquet sources — superseded by PMTiles)
# ---------------------------------------------------------------------------

class MicrosoftParquetProvider:
    """Microsoft Global Building Footprints — GeoParquet source.

    Loads country-level GeoParquet files from the Microsoft Planetary Computer
    (https://planetarycomputer.microsoft.com/dataset/ms-buildings) and serves
    polygon footprints via spatial indexing.

    Not yet implemented — raises NotImplementedError on all method calls.
    """

    def buildings_in_bbox(self, min_lon, min_lat, max_lon, max_lat, limit=500) -> dict:
        raise NotImplementedError(
            "MicrosoftParquetProvider is not yet implemented. "
            "Download the country GeoParquet shards from Microsoft Planetary Computer "
            "and wire in spatial queries (e.g. via geopandas/pyarrow)."
        )

    def building_at_point(self, lon: float, lat: float) -> Optional[dict]:
        raise NotImplementedError(
            "MicrosoftParquetProvider is not yet implemented. "
            "See buildings_in_bbox for data source details."
        )


class VidaParquetProvider:
    """VIDA Combined Building Footprints — GeoParquet source.

    VIDA merges Microsoft, OpenStreetMap, and Google Open Buildings into a
    single deduplicated global dataset (https://vida.place/datasets/buildings).
    Served via GeoParquet shards indexed on H3 or S2 cells.

    Not yet implemented — raises NotImplementedError on all method calls.
    """

    def buildings_in_bbox(self, min_lon, min_lat, max_lon, max_lat, limit=500) -> dict:
        raise NotImplementedError(
            "VidaParquetProvider is not yet implemented. "
            "Download the VIDA GeoParquet shards and wire in spatial queries."
        )

    def building_at_point(self, lon: float, lat: float) -> Optional[dict]:
        raise NotImplementedError(
            "VidaParquetProvider is not yet implemented. "
            "See buildings_in_bbox for data source details."
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

# Cache heavyweight providers (PMTiles opens a file + reads the root directory
# once; a new instance per request would be wasteful).
_PROVIDER_CACHE: dict = {}


def get_provider(name: str = "stub", pmtiles_path: Optional[str] = None) -> BuildingFootprintProvider:
    """Return the requested footprint provider.

    Parameters
    ----------
    name : str
        ``'stub'``      → StubBBoxProvider (default, always works)
        ``'pmtiles'``   → PMTilesFootprintProvider (real data; needs ``pmtiles_path``)
        ``'microsoft'`` → MicrosoftParquetProvider (raises NotImplementedError)
        ``'vida'``      → VidaParquetProvider      (raises NotImplementedError)

    Raises
    ------
    FileNotFoundError
        When ``'pmtiles'`` is requested but ``pmtiles_path`` does not exist.
    NotImplementedError
        For 'microsoft'/'vida' until the parquet providers are wired in.
    ValueError
        For completely unknown provider names.
    """
    if name == "stub":
        return StubBBoxProvider()
    if name == "pmtiles":
        key = ("pmtiles", pmtiles_path)
        prov = _PROVIDER_CACHE.get(key)
        if prov is None:
            prov = PMTilesFootprintProvider(pmtiles_path)
            _PROVIDER_CACHE[key] = prov
        return prov
    if name == "microsoft":
        raise NotImplementedError(
            "MicrosoftParquetProvider is not yet available. "
            "Use get_provider('stub') for development."
        )
    if name == "vida":
        raise NotImplementedError(
            "VidaParquetProvider is not yet available. "
            "Use get_provider('stub') for development."
        )
    raise ValueError(
        f"Unknown provider '{name}'. Valid options: 'stub', 'microsoft', 'vida'."
    )


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    provider = StubBBoxProvider()

    # --- bbox query ---
    bbox_result = provider.buildings_in_bbox(30.70, 36.90, 30.705, 36.905)
    features = bbox_result["features"]
    print(f"buildings_in_bbox: {len(features)} features")
    if features:
        first = features[0]
        print(f"  First feature id      : {first['properties']['id']}")
        print(f"  First feature area_m2 : {first['properties']['area_m2']}")
        print(f"  First feature height_m: {first['properties']['height_m']}")
        print(f"  Geometry type         : {first['geometry']['type']}")
        print(f"  Ring point count      : {len(first['geometry']['coordinates'][0])}")

    print()

    # --- point query ---
    pt_result = provider.building_at_point(30.702, 36.902)
    if pt_result:
        print(f"building_at_point(30.702, 36.902):")
        print(f"  area_m2 : {pt_result['properties']['area_m2']}")
        print(f"  height_m: {pt_result['properties']['height_m']}")
        print(f"  id      : {pt_result['properties']['id']}")
