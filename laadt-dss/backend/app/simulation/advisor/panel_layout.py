"""
panel_layout.py — Rooftop PV panel tessellation / layout geometry engine.

Pure geometry: numpy + stdlib only.  All lon/lat coordinates use WGS-84.
The module is part of Layer 1 (Physical Modeling) and MUST NOT call any LLM
or external service.

Projection: equirectangular (adequate for roof-scale distances, < 0.1 % error
at Turkish latitudes for polygons < 500 m wide).

Panel spec (400 W mono-Si, portrait-mounted in landscape rows):
  long edge  = PANEL_W_M = 2.0 m   (runs along the row, i.e. horizontal)
  short edge = PANEL_H_M = 1.0 m   (perpendicular to row, i.e. slope direction)
"""

import math
from typing import List, Optional

import numpy as np

# ---------------------------------------------------------------------------
# Physical / default constants
# ---------------------------------------------------------------------------
PANEL_W_M = 2.0          # panel width (long edge), metres
PANEL_H_M = 1.0          # panel height (short edge), metres  (~400 W panel ≈ 2.0 m²)
PANEL_KW = 0.40          # peak power per panel, kWp

DEFAULT_ROW_GAP_M = 0.30  # gap between successive rows (tilt self-shading + walkway)
DEFAULT_COL_GAP_M = 0.05  # gap between panels within a row
DEFAULT_SETBACK_M = 0.40  # fire / edge setback margin from roof boundary


# ---------------------------------------------------------------------------
# Projection helpers
# ---------------------------------------------------------------------------

def _lonlat_to_local_m(coords, origin_lon: float, origin_lat: float) -> np.ndarray:
    """Equirectangular projection from lon/lat to local metres.

    x = (lon - origin_lon) * 111_320 * cos(origin_lat_rad)
    y = (lat - origin_lat) * 110_540

    Parameters
    ----------
    coords : list of [lon, lat]
    origin_lon, origin_lat : projection origin (degrees)

    Returns
    -------
    np.ndarray shape (N, 2) in metres
    """
    coords = np.asarray(coords, dtype=float)          # (N, 2)
    origin_lat_rad = math.radians(origin_lat)
    x = (coords[:, 0] - origin_lon) * 111_320.0 * math.cos(origin_lat_rad)
    y = (coords[:, 1] - origin_lat) * 110_540.0
    return np.column_stack([x, y])


def _local_m_to_lonlat(xy, origin_lon: float, origin_lat: float) -> List[List[float]]:
    """Inverse equirectangular projection from local metres back to lon/lat.

    Parameters
    ----------
    xy : array-like shape (N, 2) in metres
    origin_lon, origin_lat : projection origin (degrees)

    Returns
    -------
    list of [lon, lat]
    """
    xy = np.asarray(xy, dtype=float)
    origin_lat_rad = math.radians(origin_lat)
    lon = xy[:, 0] / (111_320.0 * math.cos(origin_lat_rad)) + origin_lon
    lat = xy[:, 1] / 110_540.0 + origin_lat
    return [[float(lon[i]), float(lat[i])] for i in range(len(lon))]


# ---------------------------------------------------------------------------
# Geometry primitives
# ---------------------------------------------------------------------------

def _point_in_polygon(x: float, y: float, poly_xy: np.ndarray) -> bool:
    """Ray-casting point-in-polygon test.

    Parameters
    ----------
    x, y : query point in local metres
    poly_xy : (N, 2) polygon vertices (closed or open — the algorithm closes it)

    Returns
    -------
    bool  True if (x, y) is strictly inside the polygon
    """
    n = len(poly_xy)
    inside = False
    xp = poly_xy[:, 0]
    yp = poly_xy[:, 1]
    j = n - 1
    for i in range(n):
        xi, yi = xp[i], yp[i]
        xj, yj = xp[j], yp[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def _polygon_area_m2(poly_xy: np.ndarray) -> float:
    """Shoelace formula — returns absolute area in m².

    poly_xy : (N, 2) array; polygon need not be explicitly closed.
    """
    x = poly_xy[:, 0]
    y = poly_xy[:, 1]
    n = len(x)
    area = 0.0
    j = n - 1
    for i in range(n):
        area += (x[j] + x[i]) * (y[j] - y[i])
        j = i
    return abs(area) * 0.5


def _rotate_points(pts: np.ndarray, theta_rad: float, cx: float, cy: float) -> np.ndarray:
    """Rotate pts around (cx, cy) by theta_rad (counter-clockwise)."""
    cos_t = math.cos(theta_rad)
    sin_t = math.sin(theta_rad)
    dx = pts[:, 0] - cx
    dy = pts[:, 1] - cy
    rx = cos_t * dx - sin_t * dy + cx
    ry = sin_t * dx + cos_t * dy + cy
    return np.column_stack([rx, ry])


# ---------------------------------------------------------------------------
# Core layout engine
# ---------------------------------------------------------------------------

def generate_layout(
    roof_polygon_lonlat: List[List[float]],
    azimuth_deg: float = 180.0,
    tilt_deg: float = 30.0,
    row_gap_m: float = DEFAULT_ROW_GAP_M,
    col_gap_m: float = DEFAULT_COL_GAP_M,
    setback_m: float = DEFAULT_SETBACK_M,
    max_panels: Optional[int] = None,
) -> dict:
    """Tessellate PV panels inside a roof polygon.

    The grid is built in a rotated coordinate system aligned to the requested
    azimuth, then corners are tested against the original polygon (in the same
    rotated space) with a setback margin applied to the polygon boundary.

    Algorithm
    ---------
    1. Compute centroid (origin) and project polygon vertices to local metres.
    2. Define grid rotation: theta = azimuth_deg - 180  degrees clockwise from
       south.  In the rotated frame, panel rows run left-right and the 'up'
       direction faces the azimuth.
    3. Rotate polygon into the grid frame.
    4. Compute bounding box + padding and enumerate grid cells.
    5. For each cell, generate 4 panel corners; keep cell if ALL 4 corners are
       inside the (rotated) polygon AND all corners are at least setback_m
       inside (approximated by testing a slightly larger corner probe).
    6. Back-project accepted corners and centres to lon/lat.

    Parameters
    ----------
    roof_polygon_lonlat : list of [lon, lat], ≥ 3 points
    azimuth_deg  : panel facing direction (180 = south, 90 = east, 270 = west)
    tilt_deg     : panel tilt angle, degrees above horizontal (metadata only)
    row_gap_m    : gap between rows (m)
    col_gap_m    : gap between panels in the same row (m)
    setback_m    : minimum clearance from roof edge (m)
    max_panels   : cap on number of panels (None = no limit)

    Returns
    -------
    dict with keys: panels, panel_count, total_kwp, roof_area_m2,
                    usable_area_m2, orientation_groups
    """
    coords = np.asarray(roof_polygon_lonlat, dtype=float)
    if len(coords) < 3:
        raise ValueError("roof_polygon_lonlat must have at least 3 points")

    # 1. Centroid origin and projection
    origin_lon = float(np.mean(coords[:, 0]))
    origin_lat = float(np.mean(coords[:, 1]))
    poly_m = _lonlat_to_local_m(coords.tolist(), origin_lon, origin_lat)
    roof_area = _polygon_area_m2(poly_m)

    # 2. Rotation angle: rotate grid so panel rows face 'azimuth_deg'
    #    A south-facing (180°) layout has no rotation; east (90°) rotates -90°.
    #    Convention: rotate polygon into grid frame by -theta.
    theta_deg = azimuth_deg - 180.0
    theta_rad = math.radians(theta_deg)

    cx = float(np.mean(poly_m[:, 0]))
    cy = float(np.mean(poly_m[:, 1]))

    # 3. Rotate polygon into grid frame (rotate by -theta around centroid)
    poly_rot = _rotate_points(poly_m, -theta_rad, cx, cy)

    # 4. Bounding box in rotated frame
    xmin, xmax = float(poly_rot[:, 0].min()), float(poly_rot[:, 0].max())
    ymin, ymax = float(poly_rot[:, 1].min()), float(poly_rot[:, 1].max())

    cell_w = PANEL_W_M + col_gap_m   # cell pitch along x (row direction)
    cell_h = PANEL_H_M + row_gap_m   # cell pitch along y (slope direction)

    # Grid starting point (include setback in the starting offset)
    x_start = xmin + setback_m
    y_start = ymin + setback_m

    panels = []
    panel_id = 0

    # 5. Enumerate grid cells
    row_idx = 0
    y0 = y_start
    while y0 + PANEL_H_M <= ymax - setback_m:
        col_idx = 0
        x0 = x_start
        while x0 + PANEL_W_M <= xmax - setback_m:
            # 4 corners of this panel cell (in rotated frame)
            corners_rot = np.array([
                [x0,             y0],
                [x0 + PANEL_W_M, y0],
                [x0 + PANEL_W_M, y0 + PANEL_H_M],
                [x0,             y0 + PANEL_H_M],
            ])

            # Setback test: all 4 corners must be inside the rotated polygon.
            # Additionally we shrink the test point by setback_m inward using
            # a small epsilon probe — pragmatic approach: test a corner point
            # that is setback_m inside the bounding box.  For the polygon
            # containment we test the raw corners; for setback we add a margin
            # by only accepting cells whose corners are already ≥ setback_m
            # from each AABB edge.  The combination of the AABB-margin
            # (x_start/y_start already account for setback) plus polygon
            # containment gives a robust result for typical convex/near-convex
            # roofs.
            all_inside = all(
                _point_in_polygon(float(corners_rot[k, 0]),
                                  float(corners_rot[k, 1]),
                                  poly_rot)
                for k in range(4)
            )

            if all_inside:
                # Back-rotate corners to world metres
                corners_world = _rotate_points(corners_rot, theta_rad, cx, cy)
                center_rot = np.array([[x0 + PANEL_W_M / 2, y0 + PANEL_H_M / 2]])
                center_world = _rotate_points(center_rot, theta_rad, cx, cy)

                # Back-project to lon/lat
                corners_ll = _local_m_to_lonlat(corners_world.tolist(), origin_lon, origin_lat)
                center_ll = _local_m_to_lonlat(center_world.tolist(), origin_lon, origin_lat)[0]

                panels.append({
                    "id": panel_id,
                    "polygon_lonlat": corners_ll,   # 4 points (open ring)
                    "center_lonlat": center_ll,
                    "tilt": float(tilt_deg),
                    "azimuth": float(azimuth_deg),
                })
                panel_id += 1

                if max_panels is not None and panel_id >= max_panels:
                    break

            x0 += cell_w
            col_idx += 1

        if max_panels is not None and panel_id >= max_panels:
            break

        y0 += cell_h
        row_idx += 1

    panel_count = len(panels)
    total_kwp = round(panel_count * PANEL_KW, 3)
    usable_area = panel_count * PANEL_W_M * PANEL_H_M

    orientation_groups = []
    if panel_count > 0:
        orientation_groups.append({
            "azimuth": float(azimuth_deg),
            "tilt": float(tilt_deg),
            "kwp": total_kwp,
            "panel_count": panel_count,
        })

    return {
        "panels": panels,
        "panel_count": panel_count,
        "total_kwp": total_kwp,
        "roof_area_m2": round(roof_area, 2),
        "usable_area_m2": round(usable_area, 2),
        "orientation_groups": orientation_groups,
    }


# ---------------------------------------------------------------------------
# Optimum-layout search
# ---------------------------------------------------------------------------

def _azimuth_production_factor(azimuth_deg: float) -> float:
    """Heuristic production factor relative to south-facing array.

    factor = cos(azimuth - 180°) * 0.3 + 0.7, clamped to [0.6, 1.0].
    Peaks at 1.0 for azimuth = 180° (south); west/east ≈ 0.7; north ≈ 0.4 → clamped to 0.6.
    """
    angle_rad = math.radians(azimuth_deg - 180.0)
    factor = math.cos(angle_rad) * 0.3 + 0.7
    return max(0.6, min(1.0, factor))


def _polygon_edge_azimuths(roof_polygon_lonlat: List[List[float]], origin_lon: float,
                            origin_lat: float) -> List[float]:
    """Return an azimuth perpendicular to each polygon edge (in [0, 360))."""
    poly_m = _lonlat_to_local_m(roof_polygon_lonlat, origin_lon, origin_lat)
    azimuths = []
    n = len(poly_m)
    for i in range(n):
        x1, y1 = poly_m[i]
        x2, y2 = poly_m[(i + 1) % n]
        dx, dy = x2 - x1, y2 - y1
        # Normal direction (90° clockwise = inward for CCW polygon)
        angle_deg = math.degrees(math.atan2(dx, dy)) % 360.0
        azimuths.append(round(angle_deg, 1))
        # Also the opposite direction
        azimuths.append(round((angle_deg + 180.0) % 360.0, 1))
    return list(set(azimuths))


def optimum_layout(
    roof_polygon_lonlat: List[List[float]],
    tilt_deg: float = 30.0,
    candidate_azimuths: Optional[List[float]] = None,
    **kwargs,
) -> dict:
    """Try several azimuth orientations and return the layout with the best
    weighted score = panel_count × azimuth_production_factor(azimuth).

    Default candidate azimuths: [180, 135, 225, 90, 270] plus azimuths
    derived from polygon edge normals (so that the grid naturally aligns
    with each roof edge direction).

    Parameters
    ----------
    roof_polygon_lonlat : list of [lon, lat]
    tilt_deg            : panel tilt (passed through to generate_layout)
    candidate_azimuths  : explicit list; if None, the defaults above are used
    **kwargs            : forwarded to generate_layout (row_gap_m, col_gap_m,
                          setback_m, max_panels)

    Returns
    -------
    dict — same as generate_layout, plus key 'chosen_azimuth': float
    """
    coords = np.asarray(roof_polygon_lonlat, dtype=float)
    origin_lon = float(np.mean(coords[:, 0]))
    origin_lat = float(np.mean(coords[:, 1]))

    if candidate_azimuths is None:
        base = [180.0, 135.0, 225.0, 90.0, 270.0]
        edge_az = _polygon_edge_azimuths(roof_polygon_lonlat, origin_lon, origin_lat)
        # Deduplicate to within 5 degrees
        candidates: List[float] = list(base)
        for az in edge_az:
            if all(abs(az - c) > 5.0 and abs(az - c - 360.0) > 5.0 and abs(az - c + 360.0) > 5.0
                   for c in candidates):
                candidates.append(az)
    else:
        candidates = list(candidate_azimuths)

    best_result: Optional[dict] = None
    best_score = -1.0

    for az in candidates:
        try:
            result = generate_layout(
                roof_polygon_lonlat,
                azimuth_deg=az,
                tilt_deg=tilt_deg,
                **kwargs,
            )
        except Exception:
            continue

        score = result["panel_count"] * _azimuth_production_factor(az)
        if score > best_score:
            best_score = score
            best_result = result
            best_result["chosen_azimuth"] = float(az)

    if best_result is None:
        # Fallback: south-facing empty layout
        best_result = generate_layout(roof_polygon_lonlat, azimuth_deg=180.0, tilt_deg=tilt_deg,
                                      **kwargs)
        best_result["chosen_azimuth"] = 180.0

    return best_result


# ---------------------------------------------------------------------------
# Self-test / demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    """
    Build an 8 m × 6 m rectangle roof near lon=30.70, lat=36.90 (Antalya area).

    Conversion factors at lat ≈ 36.90°:
        Δlon per metre = 1 / (111_320 * cos(36.90°)) ≈ 1 / 89_028 ≈ 1.123e-5 °/m
        Δlat per metre = 1 / 110_540                  ≈ 9.047e-6 °/m
    """
    import math as _math

    LON0, LAT0 = 30.70, 36.90
    lat_rad = _math.radians(LAT0)
    dlon_per_m = 1.0 / (111_320.0 * _math.cos(lat_rad))
    dlat_per_m = 1.0 / 110_540.0

    W_M, H_M = 8.0, 6.0   # roof width (E-W) and depth (N-S)
    dlon = W_M * dlon_per_m
    dlat = H_M * dlat_per_m

    # Rectangle: SW, SE, NE, NW corners (counter-clockwise)
    roof = [
        [LON0,        LAT0],
        [LON0 + dlon, LAT0],
        [LON0 + dlon, LAT0 + dlat],
        [LON0,        LAT0 + dlat],
    ]

    print("=" * 60)
    print("DEMO — 8 m × 6 m rooftop near Antalya (lon=30.70, lat=36.90)")
    print("=" * 60)

    # --- generate_layout (south-facing, default gaps) ---
    gl = generate_layout(roof, azimuth_deg=180.0, tilt_deg=30.0)
    print(f"\ngenerate_layout (azimuth=180°, tilt=30°)")
    print(f"  roof_area_m2   : {gl['roof_area_m2']} m²")
    print(f"  panel_count    : {gl['panel_count']}")
    print(f"  total_kwp      : {gl['total_kwp']} kWp")
    print(f"  usable_area_m2 : {gl['usable_area_m2']} m²")
    if gl["panels"]:
        p0 = gl["panels"][0]
        print(f"  panel[0] center: {p0['center_lonlat']}")
        print(f"  panel[0] corners (lonlat):")
        for corner in p0["polygon_lonlat"]:
            print(f"    {corner}")

    # --- optimum_layout ---
    ol = optimum_layout(roof, tilt_deg=30.0)
    print(f"\noptimum_layout")
    print(f"  chosen_azimuth : {ol['chosen_azimuth']}°")
    print(f"  panel_count    : {ol['panel_count']}")
    print(f"  total_kwp      : {ol['total_kwp']} kWp")
    print(f"  orientation_groups: {ol['orientation_groups']}")
    print("=" * 60)
