"""
region_network.py — Synthetic Geo-Located LV Distribution Network Builder

PURPOSE:
    Build a SYNTHETIC geo-located low-voltage (0.4 kV) distribution network for
    a neighborhood defined by building footprints, run a pandapower Newton-
    Raphson load flow, and return GEO-LOCATED results suitable for a 3D map
    view (bus coordinates + voltages, cable coordinates + loading, transformer
    loading) plus aggregate grid-impact metrics.

MODELING ASSUMPTION:
    Real Turkish MV/LV topology data is not publicly available. This module
    synthesises a plausible LV network using a FEEDER TREE (Minimum Spanning
    Tree) per transformer: cables run building-to-building (as a real LV
    feeder trunk that branches along/between houses) rather than a star of
    independent radial cables. Multiple transformers, each serving a nearby
    cluster of buildings, are supported and are caller-editable (position +
    capacity). This is a documented simplification.

REFERENCE PATTERNS: app/simulation/grid/grid_model.py
"""

import math
from typing import Optional

# Bilimsel temelli yük modeli (kaynak-belgeli modüller)
from app.simulation.loads.turkey_parameters import annual_kwh_from_area, EV_PENETRATION_DEFAULT
from app.simulation.loads.demand_model import (
    velander_peak_kw, coincidence_factor, diversified_household_kw,
)
from app.simulation.loads import ev_load

# ─────────────────────────────────────────────────────────────────────────────
# Documented modeling constants
# ─────────────────────────────────────────────────────────────────────────────
LV_KV: float = 0.4          # LV nominal voltage (kV)
MV_KV: float = 10.5         # MV nominal voltage (kV)

# Peak load estimation: 100 m² building → 4 kW
PEAK_KW_PER_M2: float = 0.04

# PV capacity estimation from roof area (simplified: ~10 Wp/m² net usable)
PV_KWP_PER_M2: float = 0.10

# PV output at solar noon expressed as fraction of rated kWp
PV_NOON_FACTOR: float = 0.8

# Battery storage absorbs this fraction of the net PV export at noon
STORAGE_ABSORB_FRACTION: float = 0.5

# İki çalışma noktası (PV ve EV aynı anda olmaz):
#   'noon'    = öğle: PV enjeksiyonu + düşük gündüz yükü (insanlar dışarıda), EV yok → gerilim YÜKSELMESİ / hosting
#   'evening' = akşam pik: tam yük + EV şarjı, PV yok → gerilim DÜŞMESİ / trafo termik
DAYTIME_LOAD_FACTOR: float = 0.4      # öğle taban yükü = akşam pikinin ~%40'ı
EVENING_STORAGE_SHAVE: float = 0.3    # batarya akşam pikinin bu kadarını tıraşlar (peak shaving)

# Transformer is sized 25 % above peak demand
TRANSFORMER_SIZING_FACTOR: float = 1.25

# Otomatik trafo yerleşimi: gerçekçi olması ve yük akışının yakınsaması için
# her ~40 binaya bir trafo (gerçek AG trafoları ~30-100 hane besler)
BUILDINGS_PER_TRAFO: int = 40
MAX_AUTO_TRAFOS: int = 8

# Transformer upgrade cost (TL / kVA) for deferral benefit calculation
TRAFO_UPGRADE_COST_TL_PER_KVA: float = 1500.0

# Voltage violation limits (EN 50160 / TEDAŞ limits)
V_MAX_PU: float = 1.05
V_MIN_PU: float = 0.95

# Line / transformer overload threshold
LINE_OVERLOAD_PCT: float = 100.0

# Pandapower std_type for LV cables (feeder trunk + branches)
LV_LINE_STD_TYPE: str = "NAYY 4x150 SE"

# MV/LV dağıtım trafosu standart güç kademeleri (kVA, artan) — parametreyle kurulur
_TRAFO_SIZES_KVA = [100, 250, 400, 630, 1000, 1600, 2500, 4000]


# ─────────────────────────────────────────────────────────────────────────────
# Utility helpers
# ─────────────────────────────────────────────────────────────────────────────

def _haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Return great-circle distance in kilometres between two WGS-84 points."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2.0 * R * math.asin(math.sqrt(a))


# Public alias (per spec: "add a helper haversine_km(...) if not present")
def haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Public alias of _haversine_km — great-circle distance in km."""
    return _haversine_km(lon1, lat1, lon2, lat2)


def _pick_trafo_rating_kva(needed_kva: float) -> float:
    """En küçük standart güç kademesi (kVA) >= needed_kva; yoksa en büyüğü."""
    for kva in _TRAFO_SIZES_KVA:
        if kva >= needed_kva:
            return float(kva)
    return float(_TRAFO_SIZES_KVA[-1])


def _years_to_overload(peak_load_mw: float, rated_mva: float, growth_pct: float,
                        max_years: int = 50) -> Optional[int]:
    """
    Return the first integer year in [1, max_years] at which
    peak_load_mw * (1 + growth_pct/100)^year >= rated_mva,
    or None if it never happens within max_years.
    """
    for y in range(1, max_years + 1):
        if peak_load_mw * (1.0 + growth_pct / 100.0) ** y >= rated_mva:
            return y
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Clustering: assign each building to its nearest transformer
# ─────────────────────────────────────────────────────────────────────────────

def _auto_place_transformers(buildings: list) -> list:
    """Bina sayısına göre birden çok trafoyu k-means benzeri kümeleme ile yerleştir.
    Gerçekçi (her ~40 binaya bir trafo) ve kısa fiderler → yük akışı yakınsar."""
    n = len(buildings)
    pts = [(b["lon"], b["lat"]) for b in buildings]
    k = max(1, min((n + BUILDINGS_PER_TRAFO - 1) // BUILDINGS_PER_TRAFO, MAX_AUTO_TRAFOS))
    if k == 1:
        return [{"id": "tr1", "lon": sum(p[0] for p in pts) / n, "lat": sum(p[1] for p in pts) / n}]

    # Uzak-nokta tohumlama (farthest-point seeding)
    seeds = [0]
    while len(seeds) < k:
        best_i, best_d = -1, -1.0
        for i in range(n):
            d = min(_haversine_km(pts[i][0], pts[i][1], pts[s][0], pts[s][1]) for s in seeds)
            if d > best_d:
                best_d, best_i = d, i
        seeds.append(best_i)
    centroids = [pts[s] for s in seeds]

    # Lloyd iterasyonları
    for _ in range(6):
        groups: list = [[] for _ in range(k)]
        for i in range(n):
            ci = min(range(k), key=lambda c: _haversine_km(pts[i][0], pts[i][1], centroids[c][0], centroids[c][1]))
            groups[ci].append(i)
        new_centroids = []
        for c in range(k):
            if groups[c]:
                new_centroids.append((
                    sum(pts[i][0] for i in groups[c]) / len(groups[c]),
                    sum(pts[i][1] for i in groups[c]) / len(groups[c]),
                ))
            else:
                new_centroids.append(centroids[c])
        if new_centroids == centroids:
            break
        centroids = new_centroids

    return [{"id": f"tr{c + 1}", "lon": centroids[c][0], "lat": centroids[c][1]} for c in range(k)]


def _assign_clusters(buildings: list, transformers: list) -> dict:
    """
    Assign each building index to the nearest transformer (haversine distance).

    Returns
    -------
    dict[str, list[int]]  transformer_id -> list of building indices
    """
    clusters: dict = {t["id"]: [] for t in transformers}
    for i, bld in enumerate(buildings):
        best_id = None
        best_dist = float("inf")
        for t in transformers:
            d = _haversine_km(bld["lon"], bld["lat"], t["lon"], t["lat"])
            if d < best_dist:
                best_dist = d
                best_id = t["id"]
        clusters[best_id].append(i)
    return clusters


# ─────────────────────────────────────────────────────────────────────────────
# Minimum Spanning Tree (Prim's algorithm) over a point set rooted at index 0
# ─────────────────────────────────────────────────────────────────────────────

def _build_mst(points: list) -> list:
    """
    Build a Minimum Spanning Tree over `points` (list of (lon, lat) tuples)
    using Prim's algorithm with haversine edge weights. Rooted at points[0]
    (the transformer node in this module's usage).

    Returns
    -------
    list of (parent_idx, child_idx, dist_km) — MST edges, in the order they
    were added.  O(n^2); fine for the small clusters expected here (<=250
    total buildings across all transformers).
    """
    n = len(points)
    if n <= 1:
        return []

    in_tree = [False] * n
    in_tree[0] = True
    # best_dist[j] / best_parent[j]: cheapest known edge connecting j to the tree
    best_dist = [float("inf")] * n
    best_parent = [0] * n
    for j in range(1, n):
        best_dist[j] = _haversine_km(points[0][0], points[0][1], points[j][0], points[j][1])
        best_parent[j] = 0

    edges = []
    for _ in range(n - 1):
        # Pick the not-yet-in-tree vertex with the smallest connecting edge
        u = -1
        u_dist = float("inf")
        for j in range(n):
            if not in_tree[j] and best_dist[j] < u_dist:
                u_dist = best_dist[j]
                u = j
        if u == -1:
            break  # disconnected (shouldn't happen — complete graph)
        in_tree[u] = True
        edges.append((best_parent[u], u, best_dist[u]))

        # Relax distances to remaining vertices
        for j in range(n):
            if not in_tree[j]:
                d = _haversine_km(points[u][0], points[u][1], points[j][0], points[j][1])
                if d < best_dist[j]:
                    best_dist[j] = d
                    best_parent[j] = u

    return edges


# ─────────────────────────────────────────────────────────────────────────────
# Core network builder (single adoption level, all transformers + MST feeders)
# ─────────────────────────────────────────────────────────────────────────────

def _edge_key(from_id_local: int, to_id_local: int, tid: str) -> str:
    """Kararlı, yönden bağımsız kenar anahtarı: 'tr:<id>' ve 'b:<binaIdx>' uçlarının sıralı birleşimi."""
    fk = f"tr:{tid}" if from_id_local == -1 else f"b:{from_id_local}"
    tk = f"tr:{tid}" if to_id_local == -1 else f"b:{to_id_local}"
    return "|".join(sorted([fk, tk]))


def _build_and_run(buildings: list, transformers: list, clusters: dict,
                    pv_adoption_pct: float, with_storage: bool,
                    edge_length_overrides: Optional[dict] = None,
                    ev_penetration: float = 0.0,
                    operating_point: str = "evening") -> dict:
    """
    Build the multi-transformer MST-feeder LV network for the given buildings
    and PV adoption, run Newton-Raphson load flow, and return a raw result
    dict.  Raises ImportError if pandapower is unavailable.

    Parameters
    ----------
    buildings       : list of {'lon', 'lat', 'area_m2'}
    transformers    : list of {'id', 'lon', 'lat', 'capacity_kva'} (capacity
                      already resolved — no auto-sizing performed here)
    clusters        : dict[str, list[int]] transformer_id -> building indices
                      (from _assign_clusters)
    pv_adoption_pct : 0..100
    with_storage    : bool

    Returns
    -------
    dict with keys:
        converged, net, bus_coords (dict[int,(lon,lat)]),
        trafo_bus_lv (dict[str,int] transformer_id -> LV bus idx),
        trafo_pp_idx (dict[str,int] transformer_id -> net.trafo row idx),
        building_bus (dict[int,int] building idx -> pp bus idx),
        building_trafo (dict[int,str] building idx -> transformer_id),
        pv_bus_set (set of building indices with PV),
        mst_edges (list of (transformer_id, from_bus, to_bus, from_id_local,
                   to_id_local, dist_km) — from_id_local/to_id_local are -1
                   for the transformer root node, else building index),
        n_pv, total_pv_kwp, total_load_kw
    """
    import pandapower as pp  # imported here so import errors surface clearly

    net = pp.create_empty_network(f_hz=50.0, sn_mva=1.0)

    bus_coords: dict = {}
    trafo_bus_lv: dict = {}
    trafo_pp_idx: dict = {}
    building_bus: dict = {}
    building_trafo: dict = {}
    mst_edges = []

    n = len(buildings)
    total_load_kw = 0.0
    total_pv_kwp = 0.0
    pv_bus_set = set()
    ev_bus_set = set()

    for t in transformers:
        tid = t["id"]
        cluster_building_idxs = clusters.get(tid, [])
        cap_kva = float(t["capacity_kva"])
        sn_mva = cap_kva / 1000.0

        # ── MV slack bus + ext_grid (independent per-transformer subnetwork) ──
        bus_mv = pp.create_bus(net, vn_kv=MV_KV, name=f"MV_Slack_{tid}",
                               geodata=(t["lon"], t["lat"]))
        pp.create_ext_grid(net, bus=bus_mv, vm_pu=1.0, name=f"MV_Grid_{tid}")

        # ── LV busbar at transformer secondary (MST root for this cluster) ────
        bus_lv = pp.create_bus(net, vn_kv=LV_KV, name=f"LV_Busbar_{tid}",
                               geodata=(t["lon"], t["lat"]))
        trafo_bus_lv[tid] = bus_lv
        bus_coords[bus_lv] = (float(t["lon"]), float(t["lat"]))

        # ── Transformer (built from parameters — no std_type lookup) ─────────
        trafo_idx = pp.create_transformer_from_parameters(
            net, hv_bus=bus_mv, lv_bus=bus_lv,
            sn_mva=sn_mva, vn_hv_kv=MV_KV, vn_lv_kv=LV_KV,
            vk_percent=6.0, vkr_percent=1.5,
            pfe_kw=max(0.3, sn_mva * 1.0), i0_percent=0.5,
            name=f"MV_LV_Trafo_{tid}",
        )
        trafo_pp_idx[tid] = trafo_idx

        # ── Building buses + loads + PV for this cluster ──────────────────────
        cluster_size = len(cluster_building_idxs)
        n_pv_cluster = round(pv_adoption_pct / 100.0 * cluster_size)
        cluster_pv_set = set(cluster_building_idxs[:n_pv_cluster])
        # EV: penetrasyona göre bu kümede EV'li hane sayısı (ilk n_ev bina)
        n_ev_cluster = ev_load.ev_household_count(cluster_size, ev_penetration)
        cluster_ev_set = set(cluster_building_idxs[:n_ev_cluster])
        # EV-hane başına diversite-sonrası ek şarj yükü (kW) — akşam pikiyle çakışır
        ev_kw_per_household = ev_load.ev_diversified_household_kw(n_ev_cluster) if n_ev_cluster else 0.0

        is_evening = (operating_point == "evening")

        local_points = [(t["lon"], t["lat"])]  # index 0 = transformer/root
        local_to_global_bus = {}  # local MST index -> pp bus idx (filled below)

        for i in cluster_building_idxs:
            bld = buildings[i]
            b_bus = pp.create_bus(net, vn_kv=LV_KV, name=f"Bld_{i}",
                                  geodata=(bld["lon"], bld["lat"]))
            building_bus[i] = b_bus
            building_trafo[i] = tid
            bus_coords[b_bus] = (float(bld["lon"]), float(bld["lat"]))

            # PV/EV sahipliği (rapor için, çalışma noktasından bağımsız)
            if i in cluster_pv_set:
                pv_bus_set.add(i)
                total_pv_kwp += bld["area_m2"] * PV_KWP_PER_M2
            if i in cluster_ev_set:
                ev_bus_set.add(i)

            # Diversite-sonrası hane tepe yükü: Velander × Rusck cf(N)
            annual_kwh = annual_kwh_from_area(bld["area_m2"])
            peak_kw = diversified_household_kw(annual_kwh, cluster_size)
            if is_evening:
                # AKŞAM: tam yük + EV şarjı; PV yok; batarya peak-shaving
                load_kw = peak_kw + (ev_kw_per_household if i in cluster_ev_set else 0.0)
                if with_storage:
                    load_kw *= (1.0 - EVENING_STORAGE_SHAVE)
            else:
                # ÖĞLE: düşük gündüz yükü; EV yok (insanlar dışarıda)
                load_kw = peak_kw * DAYTIME_LOAD_FACTOR
            p_mw = load_kw / 1000.0
            total_load_kw += load_kw
            pp.create_load(net, bus=b_bus, p_mw=p_mw, q_mvar=p_mw * 0.2,
                           name=f"Load_{i}")

            # PV enjeksiyonu YALNIZCA öğle çalışma noktasında
            if (not is_evening) and (i in cluster_pv_set):
                kwp = bld["area_m2"] * PV_KWP_PER_M2
                net_p_mw = kwp * PV_NOON_FACTOR / 1000.0
                if with_storage:
                    net_p_mw *= (1.0 - STORAGE_ABSORB_FRACTION)
                pp.create_sgen(net, bus=b_bus, p_mw=net_p_mw, q_mvar=0.0,
                               name=f"PV_{i}")

            local_points.append((bld["lon"], bld["lat"]))
            local_to_global_bus[len(local_points) - 1] = b_bus

        local_to_global_bus[0] = bus_lv

        # ── MST feeder for this cluster (rooted at the transformer LV bus) ────
        edges = _build_mst(local_points)
        overrides = edge_length_overrides or {}
        for parent_local, child_local, dist_km in edges:
            from_bus_pp = local_to_global_bus[parent_local]
            to_bus_pp = local_to_global_bus[child_local]
            from_id_local = -1 if parent_local == 0 else cluster_building_idxs[parent_local - 1]
            to_id_local = -1 if child_local == 0 else cluster_building_idxs[child_local - 1]
            # Kullanıcı kabloyu büktüyse gerçek güzergâh uzunluğunu kullan (uzunluk → empedans → voltaj)
            ekey = _edge_key(from_id_local, to_id_local, tid)
            if ekey in overrides:
                length_km = max(0.02, overrides[ekey] / 1000.0)
            else:
                length_km = max(0.02, dist_km)
            pp.create_line(
                net, from_bus=from_bus_pp, to_bus=to_bus_pp,
                length_km=length_km, std_type=LV_LINE_STD_TYPE,
                name=f"Line_{tid}_{parent_local}_{child_local}",
            )
            mst_edges.append((tid, from_bus_pp, to_bus_pp, from_id_local, to_id_local, length_km))

    # ── Run load flow ─────────────────────────────────────────────────────────
    converged = False
    try:
        try:
            pp.runpp(net, numba=True)
        except Exception:
            pp.runpp(net, numba=False)
        converged = bool(net["converged"])
    except Exception:
        converged = False

    return {
        "converged": converged,
        "net": net,
        "bus_coords": bus_coords,
        "trafo_bus_lv": trafo_bus_lv,
        "trafo_pp_idx": trafo_pp_idx,
        "building_bus": building_bus,
        "building_trafo": building_trafo,
        "pv_bus_set": pv_bus_set,
        "ev_bus_set": ev_bus_set,
        "mst_edges": mst_edges,
        "n_pv": len(pv_bus_set),
        "total_pv_kwp": total_pv_kwp,
        "total_load_kw": total_load_kw,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def simulate_region(
    buildings: list,
    pv_adoption_pct: float = 40.0,
    with_storage: bool = False,
    stakeholder_type: str = "residential",
    load_growth_pct: float = 3.0,
    deferral_years: int = 15,
    run_hosting_capacity: bool = True,
    transformers: Optional[list] = None,
    edge_length_overrides: Optional[list] = None,
    ev_penetration_pct: float = 0.0,
) -> dict:
    """
    Build a synthetic geo-located LV distribution network (MST feeder tree per
    transformer, supporting multiple transformers) for a neighbourhood and
    return geo-located load-flow results plus grid metrics.

    Parameters
    ----------
    buildings : list of dict, each {'lon': float, 'lat': float, 'area_m2': float}
        WGS-84 building footprint centroids with floor area.  1–300 buildings.
    pv_adoption_pct : float, 0–100
        Percentage of buildings (per cluster) that have rooftop PV at the
        analysis instant.
    with_storage : bool
        If True, building-level battery storage absorbs STORAGE_ABSORB_FRACTION
        of the noon PV surplus, reducing net injection into the grid.
    stakeholder_type : str
        Informational; currently unused in calculations but preserved in output
        for future load-profile differentiation.
    load_growth_pct : float
        Annual load growth rate (%) for transformer deferral calculation.
    deferral_years : int
        Reference horizon (years) used in avoided_upgrade_cost_tl calculation.
    run_hosting_capacity : bool
        If True, re-runs the network at adoption levels {0, 20, 40, 60, 80, 100}%
        to find the first level that causes a voltage violation.
    transformers : list of dict or None
        Caller-editable transformers: [{'id': str, 'lon': float, 'lat': float,
        'capacity_kva': float}]. `capacity_kva` may be omitted to auto-size
        that transformer. If None/empty, exactly one transformer ('tr1') is
        auto-placed at the buildings' centroid with auto-sized capacity.

    Returns
    -------
    dict with keys:
        'transformers', 'buses', 'edges', 'metrics', 'assumption_note'

    Raises
    ------
    ValueError
        If buildings list is empty or contains fewer than 1 entry.
    """
    if not buildings or len(buildings) < 1:
        raise ValueError(
            "simulate_region requires at least 1 building in the 'buildings' list."
        )

    n = len(buildings)

    # ── Resolve transformer list (auto-place / auto-size as needed) ──────────
    lon_c = sum(b["lon"] for b in buildings) / n
    lat_c = sum(b["lat"] for b in buildings) / n

    if not transformers:
        resolved_transformers = _auto_place_transformers(buildings)
    else:
        # Shallow-copy each dict so we don't mutate caller's input
        resolved_transformers = [dict(t) for t in transformers]

    # Ensure every transformer has a non-empty, unique id (callers may omit
    # 'id' entirely, e.g. Pydantic models with id: Optional[str] = None).
    seen_ids: set = set()
    for idx, t in enumerate(resolved_transformers):
        tid = t.get("id")
        if not tid or tid in seen_ids:
            tid = f"tr{idx + 1}"
            while tid in seen_ids:
                idx += 1
                tid = f"tr{idx + 1}"
        t["id"] = tid
        seen_ids.add(tid)

    # Assign clusters first (needed to auto-size capacities per-cluster)
    clusters = _assign_clusters(buildings, resolved_transformers)

    ev_frac = max(0.0, min(1.0, ev_penetration_pct / 100.0))
    for t in resolved_transformers:
        if "capacity_kva" not in t or t["capacity_kva"] is None:
            cluster_idxs = clusters.get(t["id"], [])
            n = len(cluster_idxs)
            # Eş-zamanlı tepe = cf(N) × Σ(Velander bireysel tepe) + EV eş-zamanlı tepe
            # (yük akışındaki diversite-sonrası yüklerle tutarlı)
            sum_peaks = sum(velander_peak_kw(annual_kwh_from_area(buildings[i]["area_m2"])) for i in cluster_idxs)
            base_coincident_kw = coincidence_factor(n) * sum_peaks
            n_ev = ev_load.ev_household_count(n, ev_frac)
            ev_coincident_kw = ev_load.ev_coincident_peak_kw(n_ev)
            coincident_kw = base_coincident_kw + ev_coincident_kw
            needed_kva = max(100.0, coincident_kw * TRANSFORMER_SIZING_FACTOR)
            t["capacity_kva"] = _pick_trafo_rating_kva(needed_kva)

    transformer_count = len(resolved_transformers)

    # Kablo güzergâh (uzunluk) override'larını sözlüğe çevir: {canonical_key: length_m}
    ovr = {o["key"]: o["length_m"] for o in (edge_length_overrides or []) if o.get("key") and o.get("length_m")}

    # ── Main build + run ──────────────────────────────────────────────────────
    try:
        r = _build_and_run(buildings, resolved_transformers, clusters,
                           pv_adoption_pct, with_storage, ovr, ev_frac,
                           operating_point="evening")
    except ImportError:
        # pandapower not available — return minimal failure structure
        return {
            "transformers": [
                {
                    "id": t["id"], "lon": float(t["lon"]), "lat": float(t["lat"]),
                    "capacity_kva": float(t["capacity_kva"]),
                    "loading_percent": None, "status": "UNKNOWN",
                }
                for t in resolved_transformers
            ],
            "buses": [],
            "edges": [],
            "metrics": {
                "building_count": n,
                "pv_building_count": round(pv_adoption_pct / 100 * n),
                "pv_adoption_pct": float(pv_adoption_pct),
                "with_storage": with_storage,
                "total_pv_kwp": None,
                "total_load_kw": None,
                "transformer_count": transformer_count,
                "max_voltage_pu": None,
                "min_voltage_pu": None,
                "voltage_violation": None,
                "max_line_loading_pct": None,
                "max_transformer_loading_pct": None,
                "transformer_overload": None,
                "total_losses_kw": None,
                "reverse_power_flow": None,
                "hosting_capacity_pct": None,
                "transformer_deferral_years": None,
                "avoided_upgrade_cost_tl": None,
                "converged": False,
                "error": "pandapower not installed",
            },
            "assumption_note": (
                "Şebeke topolojisi sentetiktir (gerçek MV/LV verisi kamuya açık "
                "değil); besleyici hatlar Minimum Yayılma Ağacı (MST) modeliyle "
                "bina-bina ilerleyen bir gövde hattı olarak kurulmuştur."
            ),
        }

    converged = r["converged"]
    net = r["net"]
    bus_coords = r["bus_coords"]
    trafo_bus_lv = r["trafo_bus_lv"]
    trafo_pp_idx = r["trafo_pp_idx"]
    building_bus = r["building_bus"]
    building_trafo = r["building_trafo"]
    pv_bus_set = r["pv_bus_set"]
    ev_bus_set = r.get("ev_bus_set", set())
    mst_edges = r["mst_edges"]
    total_pv_kwp = r["total_pv_kwp"]
    total_load_kw = r["total_load_kw"]
    n_pv = r["n_pv"]

    # Pandapower bus indeksi → kararlı kenar-uç anahtarı (kablo güzergâh kalıcılığı için)
    bus_key: dict = {}
    for (tid_e, fb, tb, fidl, tidl, _len) in mst_edges:
        bus_key[fb] = f"tr:{tid_e}" if fidl == -1 else f"b:{fidl}"
        bus_key[tb] = f"tr:{tid_e}" if tidl == -1 else f"b:{tidl}"

    assumption_note = (
        "Şebeke topolojisi sentetiktir (gerçek MV/LV verisi kamuya açık "
        "değil); besleyici hatlar Minimum Yayılma Ağacı (MST) modeliyle "
        "bina-bina ilerleyen bir gövde hattı olarak kurulmuştur; "
        f"{transformer_count} trafo desteklenmektedir."
    )

    # ── If load flow did not converge: return safe zeros ─────────────────────
    if not converged:
        return {
            "transformers": [
                {
                    "id": t["id"], "lon": float(t["lon"]), "lat": float(t["lat"]),
                    "capacity_kva": float(t["capacity_kva"]),
                    "loading_percent": None, "status": "UNKNOWN",
                }
                for t in resolved_transformers
            ],
            "buses": [
                {
                    "id": int(b_idx),
                    "lon": float(buildings[i]["lon"]),
                    "lat": float(buildings[i]["lat"]),
                    "vm_pu": None,
                    "has_pv": i in pv_bus_set,
                    "status": "UNKNOWN",
                    "transformer_id": building_trafo[i],
                }
                for i, b_idx in building_bus.items()
            ],
            "edges": [],
            "metrics": {
                "building_count": n,
                "pv_building_count": n_pv,
                "pv_adoption_pct": float(pv_adoption_pct),
                "with_storage": with_storage,
                "total_pv_kwp": round(float(total_pv_kwp), 2),
                "total_load_kw": round(float(total_load_kw), 2),
                "transformer_count": transformer_count,
                "max_voltage_pu": None,
                "min_voltage_pu": None,
                "voltage_violation": None,
                "max_line_loading_pct": None,
                "max_transformer_loading_pct": None,
                "transformer_overload": None,
                "total_losses_kw": None,
                "reverse_power_flow": None,
                "hosting_capacity_pct": None,
                "transformer_deferral_years": None,
                "avoided_upgrade_cost_tl": None,
                "converged": False,
                "error": "Load flow did not converge",
            },
            "assumption_note": assumption_note,
        }

    # ── Extract transformer results ───────────────────────────────────────────
    transformers_out = []
    max_trafo_loading = 0.0
    total_trafo_capacity_kva = 0.0
    for t in resolved_transformers:
        tid = t["id"]
        cap_kva = float(t["capacity_kva"])
        total_trafo_capacity_kva += cap_kva
        pp_idx = trafo_pp_idx.get(tid)
        loading_pct = 0.0
        if pp_idx is not None and len(net.res_trafo) > 0:
            loading_pct = float(net.res_trafo.loc[pp_idx, "loading_percent"])
        max_trafo_loading = max(max_trafo_loading, loading_pct)
        status = "OVERLOAD" if loading_pct > LINE_OVERLOAD_PCT else "OK"
        transformers_out.append({
            "id": tid,
            "lon": round(float(t["lon"]), 6),
            "lat": round(float(t["lat"]), 6),
            "capacity_kva": cap_kva,
            "loading_percent": round(loading_pct, 2),
            "status": status,
        })
    transformer_overload = any(t["status"] == "OVERLOAD" for t in transformers_out)

    # ── Extract bus results (building buses only) ──────────────────────────────
    buses_out = []
    vm_values = []
    for i, b_idx in building_bus.items():
        vm_pu = float(net.res_bus.loc[b_idx, "vm_pu"])
        vm_values.append(vm_pu)
        status = "VIOLATION" if (vm_pu > V_MAX_PU or vm_pu < V_MIN_PU) else "OK"
        area = float(buildings[i]["area_m2"])
        annual_kwh = annual_kwh_from_area(area)
        peak_kw = velander_peak_kw(annual_kwh)  # hanenin bireysel tepe gücü (Velander)
        has_ev = i in ev_bus_set
        if has_ev:
            peak_kw += ev_load.EV_CHARGER_KW  # EV şarj gücü hane tepesine eklenir
        pv_kwp = round(area * PV_KWP_PER_M2, 2) if i in pv_bus_set else 0.0
        buses_out.append({
            "id": int(b_idx),
            "lon": float(buildings[i]["lon"]),
            "lat": float(buildings[i]["lat"]),
            "vm_pu": round(vm_pu, 5),
            "has_pv": i in pv_bus_set,
            "has_ev": has_ev,
            "status": status,
            "transformer_id": building_trafo[i],
            "area_m2": round(area, 1),
            "annual_kwh": round(annual_kwh),
            "peak_kw": round(peak_kw, 2),
            "load_kw": round(peak_kw, 2),  # geriye-uyum: bireysel tepe (EV dahil)
            "pv_kwp": pv_kwp,
        })

    max_vm = max(vm_values) if vm_values else 1.0
    min_vm = min(vm_values) if vm_values else 1.0
    voltage_violation = bool(max_vm > V_MAX_PU or min_vm < V_MIN_PU)

    # ── Extract edge (cable) results ──────────────────────────────────────────
    edges_out = []
    max_line_loading = 0.0
    if len(net.res_line) > 0:
        for line_idx in net.line.index:
            row = net.line.loc[line_idx]
            res_row = net.res_line.loc[line_idx]

            from_bus = int(row["from_bus"])
            to_bus = int(row["to_bus"])

            loading_pct = float(res_row["loading_percent"])
            max_line_loading = max(max_line_loading, loading_pct)

            # p_from_mw > 0 means power flows from 'from_bus' toward 'to_bus'.
            # In our MST, from_bus is always the parent (closer to the
            # transformer) so positive = supply flowing down toward the leaf/
            # building; negative = reverse/export flow.
            p_kw = float(res_row["p_from_mw"]) * 1000.0

            from_geo = bus_coords.get(from_bus, (lon_c, lat_c))
            to_geo = bus_coords.get(to_bus, (lon_c, lat_c))
            length_km = float(row["length_km"])

            line_status = "OVERLOAD" if loading_pct > LINE_OVERLOAD_PCT else "OK"
            fk = bus_key.get(from_bus, "")
            tk = bus_key.get(to_bus, "")
            edges_out.append({
                "id": int(line_idx),
                "from": [float(from_geo[0]), float(from_geo[1])],
                "to":   [float(to_geo[0]),   float(to_geo[1])],
                "from_id": from_bus,
                "to_id": to_bus,
                "from_key": fk,
                "to_key": tk,
                "key": "|".join(sorted([fk, tk])),
                "length_m": round(length_km * 1000.0, 1),
                "loading_percent": round(loading_pct, 2),
                "p_kw": round(p_kw, 3),
                "status": line_status,
            })

    # ── Losses and reverse power flow ─────────────────────────────────────────
    total_losses_kw = 0.0
    if len(net.res_line) > 0:
        total_losses_kw = float(net.res_line["pl_mw"].sum()) * 1000.0

    reverse_power_flow = False
    if len(net.res_ext_grid) > 0:
        reverse_power_flow = bool((net.res_ext_grid["p_mw"] < 0).any())

    # ── Hosting capacity sweep ────────────────────────────────────────────────
    hosting_capacity_pct: Optional[float] = None
    if run_hosting_capacity:
        hosting_capacity_pct = 100.0
        for test_pct in [0, 20, 40, 60, 80, 100]:
            try:
                r_sweep = _build_and_run(buildings, resolved_transformers, clusters,
                                         float(test_pct), with_storage, ovr, ev_frac,
                                         operating_point="noon")
                if r_sweep["converged"]:
                    sweep_net = r_sweep["net"]
                    sweep_bld_bus = r_sweep["building_bus"]
                    sweep_vms = [float(sweep_net.res_bus.loc[b, "vm_pu"])
                                 for b in sweep_bld_bus.values()]
                    if sweep_vms and (max(sweep_vms) > V_MAX_PU or min(sweep_vms) < V_MIN_PU):
                        hosting_capacity_pct = float(test_pct)
                        break
            except Exception:
                pass  # sweep errors are non-fatal

    # ── Transformer deferral (aggregate across all transformers) ─────────────
    total_rated_kva = total_trafo_capacity_kva
    rated_mva = total_rated_kva / 1000.0
    peak_load_mw = total_load_kw / 1000.0

    # Without DER: bare load growth
    y_without = _years_to_overload(peak_load_mw, rated_mva, load_growth_pct)

    # With DER: PV reduces effective peak by noon PV generation
    # (storage absorbs STORAGE_ABSORB_FRACTION additionally)
    pv_peak_reduction_mw = total_pv_kwp * PV_NOON_FACTOR / 1000.0
    if with_storage:
        pv_peak_reduction_mw += total_pv_kwp * PV_NOON_FACTOR * STORAGE_ABSORB_FRACTION / 1000.0
    effective_peak_mw = max(0.0, peak_load_mw - pv_peak_reduction_mw)
    y_with = _years_to_overload(effective_peak_mw, rated_mva, load_growth_pct)

    if y_without is None:
        deferral_val = float(deferral_years)  # transformers never overload without DER either
    elif y_with is None:
        deferral_val = float(deferral_years)  # DER prevents overload entirely
    else:
        deferral_val = float(max(0, min(y_with - y_without, deferral_years)))

    # Avoided cost: total_rated_kva * cost_per_kva, scaled by deferral fraction
    avoided_upgrade_cost_tl = (
        (deferral_val / deferral_years) * total_rated_kva * TRAFO_UPGRADE_COST_TL_PER_KVA
        if deferral_val > 0 else 0.0
    )

    # ── Öğle çalışma noktası: PV enjeksiyonu → gerilim YÜKSELMESİ / ters akış ──
    # (Akşam çalışma noktası yük+EV gerilim düşmesini verir; ikisini birleştiririz.)
    noon_max_vm, noon_reverse, noon_max_line, noon_max_trafo, noon_losses = max_vm, False, 0.0, 0.0, 0.0
    try:
        r_noon = _build_and_run(buildings, resolved_transformers, clusters,
                                pv_adoption_pct, with_storage, ovr, ev_frac,
                                operating_point="noon")
        if r_noon["converged"]:
            nnet = r_noon["net"]
            nvms = [float(nnet.res_bus.loc[b, "vm_pu"]) for b in r_noon["building_bus"].values()]
            if nvms:
                noon_max_vm = max(nvms)
            if len(nnet.res_line) > 0:
                noon_max_line = float(nnet.res_line["loading_percent"].max())
                noon_losses = float(nnet.res_line["pl_mw"].sum()) * 1000.0
            if len(nnet.res_trafo) > 0:
                noon_max_trafo = float(nnet.res_trafo["loading_percent"].max())
            if len(nnet.res_ext_grid) > 0:
                noon_reverse = bool((nnet.res_ext_grid["p_mw"] < 0).any())
    except Exception:
        pass

    merged_max_vm = max(max_vm, noon_max_vm)                 # gerilim yükselmesi öğleden
    merged_min_vm = min_vm                                    # gerilim düşmesi akşamdan (yük+EV)
    merged_voltage_violation = bool(merged_min_vm < V_MIN_PU or merged_max_vm > V_MAX_PU)
    merged_max_line = max(max_line_loading, noon_max_line)
    merged_max_trafo = max(max_trafo_loading, noon_max_trafo)
    merged_overload = bool(merged_max_trafo > LINE_OVERLOAD_PCT)
    merged_reverse = bool(reverse_power_flow or noon_reverse)
    merged_losses = max(total_losses_kw, noon_losses)

    # ── Assemble and return ───────────────────────────────────────────────────
    return {
        "transformers": transformers_out,
        "buses": buses_out,
        "edges": edges_out,
        "metrics": {
            "building_count": n,
            "pv_building_count": n_pv,
            "pv_adoption_pct": float(pv_adoption_pct),
            "ev_penetration_pct": float(ev_penetration_pct),
            "with_storage": with_storage,
            "total_pv_kwp": round(float(total_pv_kwp), 2),
            "total_load_kw": round(float(total_load_kw), 2),
            "transformer_count": transformer_count,
            "max_voltage_pu": round(float(merged_max_vm), 5),
            "min_voltage_pu": round(float(merged_min_vm), 5),
            "voltage_violation": merged_voltage_violation,
            "max_line_loading_pct": round(float(merged_max_line), 2),
            "max_transformer_loading_pct": round(float(merged_max_trafo), 2),
            "transformer_overload": merged_overload,
            "total_losses_kw": round(float(merged_losses), 4),
            "reverse_power_flow": merged_reverse,
            "hosting_capacity_pct": hosting_capacity_pct,
            "transformer_deferral_years": round(deferral_val, 2),
            "avoided_upgrade_cost_tl": round(avoided_upgrade_cost_tl, 0),
            "converged": True,
        },
        "assumption_note": assumption_note,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Quick smoke-test (run with: python region_network.py)
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        import pandapower  # noqa: F401 — just checking availability
    except ImportError:
        print("pandapower not available locally; code-review only")
        raise SystemExit(0)

    import json

    # Synthesise ~15 buildings near Antalya city centre, no transformers
    # supplied (auto-placed at centroid, auto-sized).
    base_lon, base_lat = 30.70, 36.90
    test_buildings = []
    areas = [150, 180, 200, 170, 220, 160, 190, 175, 210, 165, 185, 195, 205, 155, 230]
    for i, area in enumerate(areas):
        row = i // 4
        col = i % 4
        test_buildings.append({
            "lon": base_lon + col * 0.0003,
            "lat": base_lat + row * 0.0003,
            "area_m2": float(area),
        })

    print(f"Running simulate_region with {len(test_buildings)} buildings, "
          f"no transformers supplied (auto-placed) …")
    result = simulate_region(
        buildings=test_buildings,
        pv_adoption_pct=40.0,
        with_storage=False,
        load_growth_pct=3.0,
        deferral_years=15,
        run_hosting_capacity=True,
        transformers=None,
    )

    # Pretty-print just the metrics for brevity
    print("\n── metrics ──────────────────────────────────")
    print(json.dumps(result["metrics"], indent=2, ensure_ascii=False))
    print("\n── transformers ─────────────────────────────")
    print(json.dumps(result["transformers"], indent=2, ensure_ascii=False))
    print(f"\nBuses  : {len(result['buses'])} entries")
    print(f"Edges  : {len(result['edges'])} entries")
    print(f"\nassumption_note: {result['assumption_note']}")
