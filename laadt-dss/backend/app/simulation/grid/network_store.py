"""
NetworkStore — kullanıcı tanımlı pandapower ağlarını PostgreSQL'de saklar ve yönetir.

Görev 3.3b kapsamında yazılmıştır.

Tablo: network_configs
  id          SERIAL PRIMARY KEY
  network_id  TEXT UNIQUE NOT NULL
  name        TEXT
  net_json    TEXT NOT NULL        -- pandapower.to_json() çıktısı
  created_at  TIMESTAMPTZ
  updated_at  TIMESTAMPTZ
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import pandapower as pp
from sqlalchemy import text

from app.core.database import engine

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_DDL = """
CREATE TABLE IF NOT EXISTS network_configs (
    id          SERIAL PRIMARY KEY,
    network_id  TEXT UNIQUE NOT NULL,
    name        TEXT,
    net_json    TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_INDEX_DDL = """
CREATE INDEX IF NOT EXISTS idx_network_configs_network_id
    ON network_configs (network_id);
"""


def init_network_schema() -> None:
    with engine.begin() as conn:
        conn.execute(text(_DDL))
    with engine.begin() as conn:
        conn.execute(text(_INDEX_DDL))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ensure_bus_geodata(net: pp.pandapowerNet) -> None:
    """bus_geodata DataFrame'ini garantiye alır (bazı pandapower sürümlerinde otomatik oluşmuyor)."""
    if not hasattr(net, "bus_geodata") or net.bus_geodata is None:
        net.bus_geodata = pd.DataFrame(columns=["x", "y"], dtype=float)


def _line_params_for_std(std_type: str) -> dict:
    """pandapower std_type'ı çözümle; bilinmiyorsa NAYY 4x50 fallback kullan."""
    try:
        net_tmp = pp.create_empty_network()
        std = pp.load_std_type(net_tmp, std_type, "line")
        return {
            "r_ohm_per_km": std["r_ohm_per_km"],
            "x_ohm_per_km": std["x_ohm_per_km"],
            "c_nf_per_km": std.get("c_nf_per_km", 210.0),
            "max_i_ka": std.get("max_i_ka", 0.141),
        }
    except Exception:
        return {"r_ohm_per_km": 0.641, "x_ohm_per_km": 0.083,
                "c_nf_per_km": 210.0, "max_i_ka": 0.141}


def _trafo_params_for_std(std_type: str) -> dict:
    try:
        net_tmp = pp.create_empty_network()
        std = pp.load_std_type(net_tmp, std_type, "trafo")
        return std
    except Exception:
        return {
            "sn_mva": 0.4, "vn_hv_kv": 20.0, "vn_lv_kv": 0.4,
            "vkr_percent": 1.325, "vk_percent": 4.0,
            "pfe_kw": 1.35, "i0_percent": 0.3413,
        }


def _build_net(
    network_id: str,
    buses: list[dict],
    lines: list[dict],
    transformers: list[dict],
    loads: list[dict],
    generators: list[dict],
) -> pp.pandapowerNet:
    """JSON tanımından pandapower ağı oluşturur."""
    net = pp.create_empty_network(name=network_id, f_hz=50.0, sn_mva=1.0)
    _ensure_bus_geodata(net)

    # Bus'lar
    name_to_idx: dict[str, int] = {}
    for bus in buses:
        idx = pp.create_bus(
            net,
            vn_kv=float(bus.get("vn_kv", 0.4)),
            name=bus.get("name", f"bus_{len(name_to_idx)}"),
        )
        name_to_idx[bus["name"]] = idx
        # Koordinat bilgisi
        lat = bus.get("lat")
        lon = bus.get("lon")
        if lat is not None and lon is not None:
            net.bus_geodata.at[idx, "x"] = float(lon)
            net.bus_geodata.at[idx, "y"] = float(lat)

    # Şebeke bağlantısı (ext_grid) — ilk bus'a bağla
    if name_to_idx:
        first_bus = next(iter(name_to_idx.values()))
        pp.create_ext_grid(net, bus=first_bus, vm_pu=1.0, name="Grid Connection")

    # Hatlar
    for line in lines:
        fb = name_to_idx.get(line["from_bus"])
        tb = name_to_idx.get(line["to_bus"])
        if fb is None or tb is None:
            logger.warning("Hat tanımında bilinmeyen bus: %s", line)
            continue
        std = line.get("std_type", "")
        if std:
            try:
                pp.create_line(net, fb, tb,
                               length_km=float(line.get("length_km", 0.1)),
                               std_type=std,
                               name=line.get("name", ""))
            except Exception:
                params = _line_params_for_std(std)
                pp.create_line_from_parameters(
                    net, fb, tb,
                    length_km=float(line.get("length_km", 0.1)),
                    name=line.get("name", ""),
                    **params,
                )
        else:
            params = {
                "r_ohm_per_km": float(line.get("r_ohm_per_km", 0.641)),
                "x_ohm_per_km": float(line.get("x_ohm_per_km", 0.083)),
                "c_nf_per_km": float(line.get("c_nf_per_km", 210.0)),
                "max_i_ka": float(line.get("max_i_ka", 0.141)),
            }
            pp.create_line_from_parameters(
                net, fb, tb,
                length_km=float(line.get("length_km", 0.1)),
                name=line.get("name", ""),
                **params,
            )

    # Transformatörler
    for trafo in transformers:
        hv = name_to_idx.get(trafo["hv_bus"])
        lv = name_to_idx.get(trafo["lv_bus"])
        if hv is None or lv is None:
            logger.warning("Trafo tanımında bilinmeyen bus: %s", trafo)
            continue
        std = trafo.get("std_type", "")
        sn_mva = float(trafo.get("sn_mva", 0.4))
        try:
            if std:
                pp.create_transformer(net, hv, lv, std_type=std, name=trafo.get("name", ""))
            else:
                pp.create_transformer_from_parameters(
                    net, hv, lv,
                    sn_mva=sn_mva,
                    vn_hv_kv=float(trafo.get("vn_hv_kv", 20.0)),
                    vn_lv_kv=float(trafo.get("vn_lv_kv", 0.4)),
                    vkr_percent=float(trafo.get("vkr_percent", 1.325)),
                    vk_percent=float(trafo.get("vk_percent", 4.0)),
                    pfe_kw=float(trafo.get("pfe_kw", 1.35)),
                    i0_percent=float(trafo.get("i0_percent", 0.3413)),
                    name=trafo.get("name", ""),
                )
        except Exception as e:
            logger.warning("Trafo oluşturulamadı: %s — %s", trafo, e)

    # Yükler
    for load in loads:
        bus_idx = name_to_idx.get(load["bus"])
        if bus_idx is None:
            continue
        pp.create_load(
            net, bus=bus_idx,
            p_mw=float(load.get("p_mw", 0.01)),
            q_mvar=float(load.get("q_mvar", 0.002)),
            name=load.get("name", ""),
        )

    # Üreticiler (PV, BESS, grid bağlantısı)
    for gen in generators:
        bus_idx = name_to_idx.get(gen["bus"])
        if bus_idx is None:
            continue
        gen_type = gen.get("type", "pv")
        p_mw = float(gen.get("p_mw", 0.01))
        if gen_type in ("pv", "bess"):
            pp.create_sgen(
                net, bus=bus_idx, p_mw=p_mw, q_mvar=0.0,
                name=gen.get("name", ""), type=gen_type,
            )

    return net


# ---------------------------------------------------------------------------
# NetworkStore
# ---------------------------------------------------------------------------

class NetworkStore:

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def create(
        self,
        network_id: str,
        buses: list[dict],
        lines: list[dict] | None = None,
        transformers: list[dict] | None = None,
        loads: list[dict] | None = None,
        generators: list[dict] | None = None,
        name: str = "",
    ) -> dict:
        """
        Kullanıcı tanımlı pandapower ağı oluşturur ve PostgreSQL'e kaydeder.
        Dönüş: {network_id, name, bus_count, line_count, ...}
        """
        net = _build_net(
            network_id,
            buses,
            lines or [],
            transformers or [],
            loads or [],
            generators or [],
        )
        net_json = pp.to_json(net)
        now = datetime.now(timezone.utc)

        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO network_configs (network_id, name, net_json, created_at, updated_at) "
                    "VALUES (:nid, :nm, :nj, :ca, :ua) "
                    "ON CONFLICT (network_id) DO UPDATE "
                    "  SET name=EXCLUDED.name, net_json=EXCLUDED.net_json, updated_at=EXCLUDED.updated_at"
                ),
                {"nid": network_id, "nm": name or network_id, "nj": net_json, "ca": now, "ua": now},
            )

        return self._summary(network_id, net, name or network_id)

    def update_element(
        self,
        network_id: str,
        element_type: str,
        element_id: int,
        action: str,
        updates: dict | None = None,
    ) -> dict:
        """
        Ağdaki bir elemanı günceller veya siler.
        element_type: bus | line | trafo | load | generator
        action: update | delete
        """
        net = self._load_net(network_id)
        if net is None:
            raise ValueError(f"Ağ bulunamadı: {network_id}")

        _TABLE = {
            "bus": "bus", "line": "line", "trafo": "trafo",
            "load": "load", "generator": "sgen",
        }
        table = _TABLE.get(element_type)
        if table is None:
            raise ValueError(f"Bilinmeyen eleman tipi: {element_type}")

        df = getattr(net, table, None)
        if df is None or element_id not in df.index:
            raise ValueError(f"{element_type}[{element_id}] bulunamadı")

        _ensure_bus_geodata(net)

        if action == "delete":
            # pandapower drop helpers
            _DROPPER = {
                "bus": pp.drop_buses,
                "line": lambda n, idx: n.line.drop(index=[idx], inplace=True),
                "trafo": lambda n, idx: n.trafo.drop(index=[idx], inplace=True),
                "load": lambda n, idx: n.load.drop(index=[idx], inplace=True),
                "sgen": lambda n, idx: n.sgen.drop(index=[idx], inplace=True),
            }
            dropper = _DROPPER.get(table)
            if dropper:
                try:
                    dropper(net, [element_id] if table == "bus" else element_id)
                except Exception as e:
                    logger.warning("Silme işlemi: %s", e)
        elif action == "update" and updates:
            for col, val in updates.items():
                if col in df.columns:
                    getattr(net, table).at[element_id, col] = val
            # Koordinat güncelleme (sadece bus için)
            if element_type == "bus" and "lat" in updates:
                net.bus_geodata.at[element_id, "y"] = float(updates["lat"])
            if element_type == "bus" and "lon" in updates:
                net.bus_geodata.at[element_id, "x"] = float(updates["lon"])

        self._save_net(network_id, net)
        return self._summary(network_id, net)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_net(self, network_id: str) -> Optional[pp.pandapowerNet]:
        return self._load_net(network_id)

    def list_networks(self) -> list[dict]:
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT network_id, name, created_at, updated_at FROM network_configs ORDER BY created_at DESC")
            ).fetchall()
        return [
            {"network_id": r[0], "name": r[1],
             "created_at": r[2].isoformat() if r[2] else None,
             "updated_at": r[3].isoformat() if r[3] else None}
            for r in rows
        ]

    def delete(self, network_id: str) -> bool:
        with engine.begin() as conn:
            result = conn.execute(
                text("DELETE FROM network_configs WHERE network_id = :nid"), {"nid": network_id}
            )
        return result.rowcount > 0

    # ------------------------------------------------------------------
    # Load flow
    # ------------------------------------------------------------------

    def run_loadflow(self, network_id: str, scenario: str = "peak_load") -> dict:
        """
        Newton-Raphson yük akışı çalıştırır.
        Dönüş formatı harita katmanına doğrudan aktarılabilir.
        """
        net = self._load_net(network_id)
        if net is None:
            raise ValueError(f"Ağ bulunamadı: {network_id}")
        _ensure_bus_geodata(net)

        # Senaryo modifikasyonları
        if scenario == "max_pv" and not net.sgen.empty:
            net.sgen["in_service"] = True
        elif scenario == "min_load" and not net.load.empty:
            net.load["p_mw"] = net.load["p_mw"] * 0.3
        # peak_load ve custom: değişiklik yok

        try:
            pp.runpp(net, algorithm="nr", numba=False, verbose=False)
            converged = bool(net.converged)
        except Exception as e:
            return {
                "converged": False,
                "error": str(e),
                "buses": [], "lines": [], "trafos": [],
                "summary": {"converged": False},
            }

        # Bus sonuçları
        buses_out = []
        for idx, row in net.res_bus.iterrows():
            bus_row = net.bus.loc[idx]
            geo_x = net.bus_geodata.at[idx, "x"] if idx in net.bus_geodata.index else None
            geo_y = net.bus_geodata.at[idx, "y"] if idx in net.bus_geodata.index else None
            buses_out.append({
                "id": int(idx),
                "name": str(bus_row.get("name", "")),
                "vn_kv": float(bus_row.get("vn_kv", 0)),
                "vm_pu": round(float(row.vm_pu), 6),
                "va_degree": round(float(row.va_degree), 4),
                "p_mw": round(float(row.p_mw), 6),
                "q_mvar": round(float(row.q_mvar), 6),
                "lon": float(geo_x) if geo_x is not None else None,
                "lat": float(geo_y) if geo_y is not None else None,
            })

        # Hat sonuçları
        lines_out = []
        if not net.res_line.empty:
            for idx, row in net.res_line.iterrows():
                line_row = net.line.loc[idx]
                lines_out.append({
                    "id": int(idx),
                    "name": str(line_row.get("name", "")),
                    "from_bus": int(line_row.from_bus),
                    "to_bus": int(line_row.to_bus),
                    "loading_pct": round(float(row.loading_percent), 2),
                    "p_from_mw": round(float(row.p_from_mw), 6),
                    "i_ka": round(float(row.i_from_ka), 6),
                    "overloaded": bool(row.loading_percent > 100),
                })

        # Trafo sonuçları
        trafos_out = []
        if not net.res_trafo.empty:
            for idx, row in net.res_trafo.iterrows():
                trafo_row = net.trafo.loc[idx]
                trafos_out.append({
                    "id": int(idx),
                    "name": str(trafo_row.get("name", "")),
                    "hv_bus": int(trafo_row.hv_bus),
                    "lv_bus": int(trafo_row.lv_bus),
                    "loading_pct": round(float(row.loading_percent), 2),
                    "overloaded": bool(row.loading_percent > 100),
                })

        vm_pu_series = net.res_bus.vm_pu
        summary = {
            "converged": converged,
            "max_vm_pu": round(float(vm_pu_series.max()), 6),
            "min_vm_pu": round(float(vm_pu_series.min()), 6),
            "voltage_violation": bool((vm_pu_series > 1.05).any() or (vm_pu_series < 0.95).any()),
            "total_losses_mw": round(float(net.res_line.pl_mw.sum()) if not net.res_line.empty else 0.0, 6),
            "line_overload": bool(not net.res_line.empty and (net.res_line.loading_percent > 100).any()),
        }

        # Sonuçları kaydet
        self._save_net(network_id, net)

        return {
            "converged": converged,
            "buses": buses_out,
            "lines": lines_out,
            "trafos": trafos_out,
            "summary": summary,
        }

    # ------------------------------------------------------------------
    # GeoJSON (Leaflet için)
    # ------------------------------------------------------------------

    def get_geojson(self, network_id: str) -> dict:
        """Ağ topolojisini GeoJSON formatında döner (Leaflet'e doğrudan aktarılabilir)."""
        net = self._load_net(network_id)
        if net is None:
            raise ValueError(f"Ağ bulunamadı: {network_id}")
        _ensure_bus_geodata(net)

        features = []

        # Bus'lar → Point
        for idx, row in net.bus.iterrows():
            lon = net.bus_geodata.at[idx, "x"] if idx in net.bus_geodata.index else None
            lat = net.bus_geodata.at[idx, "y"] if idx in net.bus_geodata.index else None
            if lon is None or lat is None:
                continue
            # Yük akışı sonucu varsa ekle
            vm_pu = None
            if not net.res_bus.empty and idx in net.res_bus.index:
                vm_pu = round(float(net.res_bus.at[idx, "vm_pu"]), 5)
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [float(lon), float(lat)]},
                "properties": {
                    "id": int(idx), "name": str(row.get("name", "")),
                    "element_type": "bus", "vn_kv": float(row.get("vn_kv", 0.4)),
                    "vm_pu": vm_pu,
                },
            })

        # Hatlar → LineString
        for idx, row in net.line.iterrows():
            fb, tb = int(row.from_bus), int(row.to_bus)
            coords_from = (
                [float(net.bus_geodata.at[fb, "x"]), float(net.bus_geodata.at[fb, "y"])]
                if fb in net.bus_geodata.index else None
            )
            coords_to = (
                [float(net.bus_geodata.at[tb, "x"]), float(net.bus_geodata.at[tb, "y"])]
                if tb in net.bus_geodata.index else None
            )
            if coords_from is None or coords_to is None:
                continue
            loading = None
            if not net.res_line.empty and idx in net.res_line.index:
                loading = round(float(net.res_line.at[idx, "loading_percent"]), 2)
            features.append({
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": [coords_from, coords_to]},
                "properties": {
                    "id": int(idx), "name": str(row.get("name", "")),
                    "element_type": "line",
                    "from_bus": fb, "to_bus": tb,
                    "loading_pct": loading,
                },
            })

        return {"type": "FeatureCollection", "features": features}

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_net(self, network_id: str) -> Optional[pp.pandapowerNet]:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT net_json FROM network_configs WHERE network_id = :nid"),
                {"nid": network_id},
            ).fetchone()
        if row is None:
            return None
        net = pp.from_json_string(row[0])
        _ensure_bus_geodata(net)
        return net

    def _save_net(self, network_id: str, net: pp.pandapowerNet) -> None:
        net_json = pp.to_json(net)
        now = datetime.now(timezone.utc)
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE network_configs SET net_json=:nj, updated_at=:ua "
                    "WHERE network_id=:nid"
                ),
                {"nj": net_json, "ua": now, "nid": network_id},
            )

    def _summary(self, network_id: str, net: pp.pandapowerNet, name: str = "") -> dict:
        _ensure_bus_geodata(net)
        return {
            "network_id": network_id,
            "name": name or network_id,
            "bus_count": len(net.bus),
            "line_count": len(net.line),
            "trafo_count": len(net.trafo),
            "load_count": len(net.load),
            "generator_count": len(net.sgen),
            "has_geodata": not net.bus_geodata.empty,
        }


# Module-level singleton
network_store = NetworkStore()
