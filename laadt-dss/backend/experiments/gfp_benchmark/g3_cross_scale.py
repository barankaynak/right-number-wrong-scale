"""G3 — Cross-scale sessiz geçersizlik (agregat gösterimi, GERÇEK olgu).

İDDİA (H_G3): Her müşterinin KENDİ tüketimine göre optimal (grid-kör, net-zero) PV
kararı, gerçek bir dağıtım fiderinde TOPLANDIĞINDA gerilim/termal limitleri aşabilir —
hiçbir bina-ölçekli analizin göremeyeceği, FİDER-BAĞIMLI bir cross-scale geçersizlik.
Her müşterinin sayısı bina-ölçeğinde DOĞRU; agregatın geçerliliği bina-ölçeğinde
KARAR-VERİLEMEZ (fidere bağlı). Bu, GFP ölçek-geçerliliği alanının koruduğu olgunun
enjekte-EDİLMEMİŞ, saha-benzeri kanıtı (G4 enjeksiyon-yeteneğinin tamamlayıcısı).

Danışman v2.13 tasarımı:
- Boyutlama BİRİNCİL = net-zero (`demand_to_kwp`, grid-kör; TR-mahsup + sözleşme-gücü
  ile içsel-rasyonel, muhafazakâr). Agresif kural YOK ("tuned" damgası) — bunun yerine
  kritik-ölçekleme f* sweep tek duyarlılık.
- ÇİFT KRİTER: (a) EN 50160 mutlak Vmax>1.05 @ teslim-slack (SimBench 1.025);
  (b) slack-BAĞIMSIZ gerilim-yükselişi ΔV>%3 (VDE-AR-N 4105); + trafo/hat >%100.
- Metrik: kanal-başına doğrudan-ihlal (f=1) + severity + KRİTİK ÖLÇEKLEME FAKTÖRÜ f*
  (gerçek yerleşim × f, bisection ile ilk-ihlal). uniform-hosting aşımı KULLANILMAZ
  (non-uniform agregatta tutarsız).
- İşletim-noktası: yük 0.20 × PV-tepe 0.85 BİRİNCİL (EPRI min-daytime-load; %20
  aralık-ortası) + duyarlılık ızgarası {0.10,0.20,0.30}×slack{1.000,1.025}.
- Yerleşik SimBench sgen SIFIRLANIR (rural1'de ~468 kW gömülü PV — tüm üretimi deney kontrol eder).

NOT: SimBench LV yükleri "müşteri/bağlantı-noktası"dır (hane DEĞİL — 1.5-41.6 MWh/yıl
aralığı ticari/tarımsal müşteri içerir). BESS G3'te YOK (çıplak PV; öğle-tepesinde
batarya zaten dolu, Moshövel 2015 — kapsam-adlandırma).

Kullanım: python -m experiments.gfp_benchmark.g3_cross_scale [--region CODE | --all]
"""
from __future__ import annotations
import argparse
import json

import pandapower as pp
import simbench as sb

from app.simulation.advisor.sizing import demand_to_kwp

# --- donmuş parametreler (A12 ön-kayıt-eki) ---
V_ABS_UPPER = 1.05       # EN 50160 mutlak üst-sınır (pu) @ teslim-slack
DV_LIMIT = 0.03          # VDE-AR-N 4105 slack-bağımsız gerilim-yükselişi (3%)
THERMAL_LIMIT = 100.0    # trafo/hat yüklenme %
PV_PEAK_FACTOR = 0.85    # açık-gökyüzü öğle çıkışı (rated kWp oranı)
LOAD_FACTOR = 0.20       # öğle min-yük (EPRI konvansiyonu; aralık-ortası)
SLACK_DELIVERED = 1.025  # SimBench ext_grid slack (teslim gerilimi)
LV_CODES = ["1-LV-rural1--1-sw", "1-LV-rural2--1-sw", "1-LV-rural3--1-sw",
            "1-LV-semiurb4--1-sw", "1-LV-semiurb5--1-sw", "1-LV-urban6--1-sw"]


def _fresh_net(region_id, slack_vm=SLACK_DELIVERED):
    """SimBench fideri; YERLEŞİK TÜM DER (sgen + storage + gen) SIFIRLANIR — SimBench'in
    kendi DER varsayımları (rural1'de ~468 kW sgen + 4 storage ~150 kW) deneyi kirletir;
    tüm üretimi bu deney kontrol eder. Çıplak yük ağından başlanır. ext_grid slack=1.025 pu."""
    net = sb.get_simbench_net(region_id)
    for tbl in ("sgen", "storage", "gen"):
        df = getattr(net, tbl)
        if len(df):
            for col in ("p_mw", "q_mvar"):
                if col in df.columns:
                    df[col] = 0.0
    net.ext_grid["vm_pu"] = slack_vm
    return net


def _runpp(net) -> bool:
    try:
        try:
            pp.runpp(net, algorithm="nr", numba=True)
        except Exception:
            pp.runpp(net, algorithm="nr", numba=False)
        return bool(net["converged"])
    except Exception:
        return False


def _solve(region_id, bus_kwp, load_factor, slack_vm, base_vm=None) -> dict:
    """PV yerleşimini işletim-noktasında çöz; base_vm verilirse ΔV hesapla."""
    net = _fresh_net(region_id, slack_vm)
    net.load["p_mw"] *= load_factor
    net.load["q_mvar"] *= load_factor
    for bus, kwp in bus_kwp.items():
        if kwp > 0:
            pp.create_sgen(net, bus=int(bus), p_mw=kwp / 1000.0 * PV_PEAK_FACTOR, q_mvar=0.0)
    if not _runpp(net):
        return {"converged": False}
    # G3-R7 güç-dengesi invariant'ı (danışman v2.13.10): ext+sgen−load−(hat+trafo kaybı) ≈ 0.
    # Storage-kontaminasyonu (G3-V1) tam bunu ~150 kW bozuyordu; kalıcı CI-kontrolü.
    losses = float(net.res_line["pl_mw"].sum()) + float(net.res_trafo["pl_mw"].sum())
    bal = float(net.res_ext_grid["p_mw"].sum() + net.sgen["p_mw"].sum()
                - net.load["p_mw"].sum() - losses)
    scale = float(net.sgen["p_mw"].sum() + net.load["p_mw"].sum()) or 1.0
    if abs(bal) > 0.01 * scale:
        raise AssertionError(f"G3-R7 güç-dengesi ihlali: {bal:.4f} MW (yerleşik DER sızıntısı?)")
    v = net.res_bus["vm_pu"]
    vmax = float(v.max())
    dv = None
    if base_vm is not None:
        dv = float((v - base_vm).max())      # slack-bağımsız gerilim-yükselişi
    trafo = float(net.res_trafo["loading_percent"].max()) if len(net.res_trafo) else 0.0
    line = float(net.res_line["loading_percent"].max()) if len(net.res_line) else 0.0
    return {"converged": True, "vmax_pu": round(vmax, 4), "vmin_pu": round(float(v.min()), 4),
            "max_dv_pct": round(dv * 100, 2) if dv is not None else None,
            "trafo_pct": round(trafo, 1), "line_pct": round(line, 1),
            "reverse_power": bool(net.res_ext_grid["p_mw"].sum() < 0),
            "_vbus": v}


def _base_vbus(region_id, load_factor, slack_vm):
    """PV'siz baz gerilim profili (ΔV referansı)."""
    net = _fresh_net(region_id, slack_vm)
    net.load["p_mw"] *= load_factor
    net.load["q_mvar"] *= load_factor
    if not _runpp(net):
        return None
    return net.res_bus["vm_pu"]


def _criteria(res) -> dict:
    """Kanal-başına ihlal bayrakları (çift-kriter + termal)."""
    if not res.get("converged"):
        return {}
    return {
        "voltage_abs_EN50160": bool(res["vmax_pu"] > V_ABS_UPPER),           # slack-bağımlı
        "voltage_rise_dV3pct": (bool(res["max_dv_pct"] > DV_LIMIT * 100)
                                if res.get("max_dv_pct") is not None else None),  # slack-bağımsız
        "trafo_overload": bool(res["trafo_pct"] > THERMAL_LIMIT),
        "line_overload": bool(res["line_pct"] > THERMAL_LIMIT),
    }


def _violates(region_id, bus_kwp, f, load_factor, slack_vm, base_vm, criterion) -> bool:
    scaled = {b: k * f for b, k in bus_kwp.items()}
    c = _criteria(_solve(region_id, scaled, load_factor, slack_vm, base_vm))
    return bool(c.get(criterion))


def _f_star(region_id, bus_kwp, load_factor, slack_vm, base_vm, criterion,
            f_hi=5.0, tol=0.02) -> float | None:
    """Kritik ölçekleme faktörü: gerçek yerleşim × f'in ilk-ihlal ettiği f (bisection).
    <1 → gerçek yerleşim zaten ihlal; None → f_hi'ye kadar ihlal yok."""
    if _violates(region_id, bus_kwp, tol, load_factor, slack_vm, base_vm, criterion):
        return round(tol, 2)                      # neredeyse-0'da bile ihlal
    if not _violates(region_id, bus_kwp, f_hi, load_factor, slack_vm, base_vm, criterion):
        return None
    lo, hi = tol, f_hi
    while hi - lo > tol:
        mid = (lo + hi) / 2
        if _violates(region_id, bus_kwp, mid, load_factor, slack_vm, base_vm, criterion):
            hi = mid
        else:
            lo = mid
    return round(hi, 2)


def _building_optimal(net) -> tuple[dict, list]:
    """Müşteri-başına net-zero (grid-kör) PV → bus→kWp + döküm."""
    prof = sb.get_absolute_values(net, profiles_instead_of_study_cases=True)
    ann_mwh = prof[("load", "p_mw")].sum(axis=0) * 0.25
    bus_kwp: dict = {}
    per = []
    for i, row in net.load.iterrows():
        kwh = float(ann_mwh[i]) * 1000.0
        kwp = demand_to_kwp(kwh)
        bus = int(row["bus"])
        bus_kwp[bus] = bus_kwp.get(bus, 0.0) + kwp
        per.append({"customer": int(i), "bus": bus, "annual_kwh": round(kwh, 0),
                    "kwp": round(kwp, 2)})
    return bus_kwp, per


def run(region_id: str) -> dict:
    net = _fresh_net(region_id)
    bus_kwp, per = _building_optimal(net)
    total_kwp = sum(p["kwp"] for p in per)

    # birincil işletim-noktası
    base = _base_vbus(region_id, LOAD_FACTOR, SLACK_DELIVERED)
    prim = _solve(region_id, bus_kwp, LOAD_FACTOR, SLACK_DELIVERED, base)
    prim.pop("_vbus", None)
    crit = _criteria({**prim, "converged": True})
    fstar = {c: _f_star(region_id, bus_kwp, LOAD_FACTOR, SLACK_DELIVERED, base, c)
             for c in ("voltage_abs_EN50160", "voltage_rise_dV3pct", "trafo_overload")}

    # duyarlılık ızgarası {load}×{slack}
    grid = {}
    for lf in (0.10, 0.20, 0.30):
        for sv in (1.000, 1.025):
            b = _base_vbus(region_id, lf, sv)
            r = _solve(region_id, bus_kwp, lf, sv, b)
            r.pop("_vbus", None)
            grid[f"load{lf:.2f}_slack{sv:.3f}"] = {
                "vmax_pu": r.get("vmax_pu"), "max_dv_pct": r.get("max_dv_pct"),
                "trafo_pct": r.get("trafo_pct"), **_criteria({**r, "converged": r.get("converged")})}

    return {
        "region": region_id,
        "n_customers": len(per),
        "feeder_annual_mwh": round(sum(p["annual_kwh"] for p in per) / 1000.0, 1),
        "feeder_peak_load_kw": round(float(net.load["p_mw"].sum()) * 1000.0, 1),
        "trafo_sn_kva": round(float(net.trafo["sn_mva"].iloc[0]) * 1000.0, 0),
        "aggregate_building_optimal_kwp": round(total_kwp, 1),
        "primary_operating_point": {**prim, "criteria": crit},
        "critical_scaling_factor_fstar": fstar,
        "sensitivity_grid": grid,
        "per_customer": per,
        "params": {"sizing": "net-zero demand_to_kwp (grid-blind)",
                   "load_factor": LOAD_FACTOR, "pv_peak_factor": PV_PEAK_FACTOR,
                   "slack_delivered": SLACK_DELIVERED, "v_abs_upper": V_ABS_UPPER,
                   "dv_limit_pct": DV_LIMIT * 100,
                   "simbench": sb.__version__ if hasattr(sb, "__version__") else "?",
                   "pandapower": pp.__version__},
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", default="1-LV-rural1--1-sw")
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    if a.all:
        out = {c: run(c) for c in LV_CODES}
    else:
        out = run(a.region)
    print(json.dumps(out, ensure_ascii=False, indent=2))
