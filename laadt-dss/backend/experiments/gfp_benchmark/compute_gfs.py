"""
compute_gfs.py — ÖN-KAYITLI analiz script'i (F3; PREREGISTRATION §3, §6).

Ham G1 izlerinden (run_benchmark JSONL) GFS hesaplar ve ön-kayıtlı istatistikleri
koşar. Bu dosya donmada HASH'lenir — donma sonrası değişiklik amendment gerektirir.

GFS (ön-kayıtlı birincil tanım, eşit ağırlık):
    GFS = GROUNDED / (GROUNDED + UNGROUNDED + SCALE_VIOLATION + UNIT_MISMATCH)
    (IGNORED payda-dışı; payda=0 → yanıt GFS'ten hariç, oranı raporlanır)

Notlama kaynakları:
    - G1 kol-kıyası (H_G1a/b) → reference_check   (kol-bağımsız tam-zincir referans)
    - G2 zincir-etkisi        → in-run provenance (grounded_noguard kolu; KRİTİK-7:
      referans ikincil — in-run'un kalıntı karıştırıcısı H_G2 ALEYHİNE/muhafazakâr)
    - H_G1b ikincil           → pre_intervention bileşenleri

Dışlamalar (kayıtlı): fallback=True; error!=None; reference invalid (yalnız
referans-temelli analizden); payda=0.

Kullanım: python -m experiments.gfp_benchmark.compute_gfs results/raw_g1_*.jsonl
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from itertools import combinations
from pathlib import Path

import numpy as np
from scipy import stats

BOOT_N = 10_000
BOOT_SEED = 20260708
VIOLATION_KEYS = ("UNGROUNDED", "SCALE_VIOLATION", "UNIT_MISMATCH")


# ── GFS ──────────────────────────────────────────────────────────────────────

def gfs_from_counts(counts: dict | None) -> float | None:
    if not counts:
        return None
    g = counts.get("GROUNDED", 0)
    denom = g + sum(counts.get(k, 0) for k in VIOLATION_KEYS)
    return (g / denom) if denom > 0 else None


def load_rows(paths: list[Path]) -> list[dict]:
    rows = []
    for p in paths:
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


def extract(rows: list[dict]) -> tuple[list[dict], dict]:
    """Satır → analiz kaydı; ön-kayıtlı dışlamaları uygular ve sayar."""
    out, excl = [], {"fallback": 0, "error": 0, "ref_invalid": 0,
                     "no_claims_ref": 0, "no_claims_inrun": 0, "total": 0}
    for r in rows:
        excl["total"] += 1
        if r.get("fallback"):
            excl["fallback"] += 1
            continue
        if r.get("error"):
            excl["error"] += 1
            continue
        ref = r.get("reference_check") or {}
        if ref.get("invalid"):
            excl["ref_invalid"] += 1
            ref_gfs = None
        else:
            ref_gfs = gfs_from_counts(ref.get("counts"))
            if ref_gfs is None:
                excl["no_claims_ref"] += 1
        prov = r.get("provenance") or {}
        inrun_gfs = gfs_from_counts(prov.get("counts"))
        pre = (prov.get("pre_intervention") or {})
        pre_gfs = gfs_from_counts(pre.get("counts"))
        # A21: guard v4.2 boş-grafı da değerlendirir. In-run temelli analizler (G1b
        # ön-müdahale, G2) Temmuz popülasyonunda kalır: ≥1 provenance kaydı olan yanıtlar
        # (araç çağrılmadıysa zincir uzunluğu tanımsız; boş-graf skoru = araç-kullanım oranı).
        toolless = bool(prov) and prov.get("n_records") == 0
        if toolless:
            inrun_gfs = pre_gfs = None
        if inrun_gfs is None:
            excl["no_claims_inrun"] += 1
        q = r["question"]
        out.append({
            "qid": q["id"], "config": r["config"], "repeat": r.get("repeat", 0),
            "model": r.get("model"), "chain": q.get("chain_length", 1),
            "stakeholder": q.get("stakeholder"),
            "ref_gfs": ref_gfs, "inrun_gfs": inrun_gfs, "pre_gfs": pre_gfs,
            "blocked": bool(prov.get("blocked")), "retried": bool(prov.get("retried")),
            "ambiguous": (prov.get("ambiguous_matches") or 0),
            "toolless": toolless, "evaluated": bool(prov),
            # A21-E1: withheld = guard-kolunda müdahale (retry/blok) sonrası teslim metni
            # skorlanabilir iddia taşımayan yanıt (boş-graf blok mesajı / sayısız düzeltme)
            "withheld": (r["config"] == "grounded_guard" and ref_gfs is None
                         and not ref.get("invalid")
                         and bool(prov.get("blocked") or prov.get("retried"))),
        })
    return out, excl


def cell_means(recs: list[dict], metric: str, by_model: bool = False) -> dict:
    """Hücre → tekrar-ortalaması (analiz birimi, prereg §6.1). by_model=False:
    anahtar (qid, config) — tek-model invokasyonu varsayar (prereg §7). by_model=True:
    anahtar (model, qid, config) — yalnız havuzlanmış duyarlılık analizi için."""
    cells: dict = {}
    for r in recs:
        v = r[metric]
        if v is None:
            continue
        key = (r["model"], r["qid"], r["config"]) if by_model else (r["qid"], r["config"])
        cells.setdefault(key, []).append(v)
    return {k: float(np.mean(v)) for k, v in cells.items()}


def within_repeat_variance(recs: list[dict], metric: str) -> dict:
    """F7-3: hücre-içi (tekrarlar arası) std dağılımı — tekrarlanabilirlik kanıtı.
    Tekrar sayısı 1 olan hücreler (varyans tanımsız) hariç."""
    cells: dict = {}
    for r in recs:
        v = r[metric]
        if v is None:
            continue
        cells.setdefault((r["qid"], r["config"]), []).append(v)
    stds = [float(np.std(v, ddof=0)) for v in cells.values() if len(v) > 1]
    if not stds:
        return {"n_cells_multi_repeat": 0, "note": "çok-tekrarlı hücre yok"}
    return {"n_cells_multi_repeat": len(stds),
            "mean_cell_std": round(float(np.mean(stds)), 4),
            "median_cell_std": round(float(np.median(stds)), 4),
            "max_cell_std": round(float(np.max(stds)), 4),
            "frac_cells_std_zero": round(sum(s == 0 for s in stds) / len(stds), 3)}


# ── İstatistikler (ön-kayıtlı) ───────────────────────────────────────────────

def paired_arrays(cells: dict, cfg_a: str, cfg_b: str) -> tuple[np.ndarray, np.ndarray]:
    qids = sorted({q for (q, c) in cells if c == cfg_a} &
                  {q for (q, c) in cells if c == cfg_b})
    a = np.array([cells[(q, cfg_a)] for q in qids])
    b = np.array([cells[(q, cfg_b)] for q in qids])
    return a, b


def wilcoxon_pair(a: np.ndarray, b: np.ndarray) -> dict:
    d = a - b
    if np.allclose(d, 0):
        return {"n": len(a), "stat": None, "p": 1.0, "note": "tüm farklar 0"}
    res = stats.wilcoxon(a, b, zero_method="wilcox", alternative="two-sided")
    return {"n": len(a), "stat": float(res.statistic), "p": float(res.pvalue)}


def mcnemar_exact(a_clean: np.ndarray, b_clean: np.ndarray) -> dict:
    """Yanıt-düzeyi 'tam-temiz (GFS=1)' ikilisi için exact McNemar (binom)."""
    b01 = int(np.sum((a_clean == 1) & (b_clean == 0)))
    b10 = int(np.sum((a_clean == 0) & (b_clean == 1)))
    n = b01 + b10
    p = 1.0 if n == 0 else min(1.0, 2 * stats.binom.cdf(min(b01, b10), n, 0.5))
    return {"discordant": n, "a_only": b01, "b_only": b10, "p": float(p)}


def bootstrap_diff_ci(a: np.ndarray, b: np.ndarray) -> dict:
    rng = np.random.default_rng(BOOT_SEED)
    idx = rng.integers(0, len(a), size=(BOOT_N, len(a)))
    diffs = (a[idx] - b[idx]).mean(axis=1)
    return {"mean_diff": float(np.mean(a - b)),
            "ci95": [float(np.percentile(diffs, 2.5)),
                     float(np.percentile(diffs, 97.5))]}


def holm(pvals: dict) -> dict:
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m = len(items)
    out, running_max = {}, 0.0
    for i, (k, p) in enumerate(items):
        adj = min(1.0, (m - i) * p)
        running_max = max(running_max, adj)
        out[k] = running_max
    return out


def dunn_posthoc(groups: dict) -> dict:
    """Kruskal-Wallis sonrası Dunn z-testleri (Holm ile)."""
    all_vals = np.concatenate(list(groups.values()))
    ranks = stats.rankdata(all_vals)
    n_total = len(all_vals)
    # grup ortalama rankları
    pos, mean_rank, sizes = 0, {}, {}
    for k, v in groups.items():
        mean_rank[k] = float(np.mean(ranks[pos:pos + len(v)]))
        sizes[k] = len(v)
        pos += len(v)
    # bağ düzeltmesi
    _, tie_counts = np.unique(all_vals, return_counts=True)
    tie_term = float(np.sum(tie_counts ** 3 - tie_counts))
    pvals = {}
    for k1, k2 in combinations(groups, 2):
        se = math.sqrt((n_total * (n_total + 1) / 12.0
                        - tie_term / (12.0 * (n_total - 1)))
                       * (1.0 / sizes[k1] + 1.0 / sizes[k2]))
        z = abs(mean_rank[k1] - mean_rank[k2]) / se if se > 0 else 0.0
        pvals[f"{k1}-vs-{k2}"] = float(2 * (1 - stats.norm.cdf(z)))
    return {"pairwise_p": pvals, "pairwise_p_holm": holm(pvals)}


# ── Analizler ────────────────────────────────────────────────────────────────

def analyze_one_model(recs: list[dict], excl: dict, model: str) -> dict:
    """BİRİNCİL analiz — TEK model (prereg §7 invokasyon protokolü). Tüm hücre-
    ortalamaları ve istatistikler bu modelin kayıtları üzerinde; modeller-arası
    karışma YOK."""
    rep: dict = {"model": model, "exclusions": excl}
    excl_rate = ((excl["fallback"] + excl["error"]) / excl["total"]
                 if excl["total"] else 0.0)
    rep["exclusion_rate"] = round(excl_rate, 4)
    rep["exclusion_rate_over_10pct_INVALID"] = excl_rate > 0.10   # prereg §6.6

    # F7-3: tekrarlanabilirlik — hücre-içi (tekrarlar arası) varyans
    rep["within_repeat_variance"] = {
        "ref_gfs": within_repeat_variance(recs, "ref_gfs"),
        "inrun_gfs": within_repeat_variance(recs, "inrun_gfs"),
    }

    # H_G1a / H_G1b — referans-GFS, eşleştirilmiş kol kıyasları
    ref_cells = cell_means(recs, "ref_gfs")
    pairs = [("grounded_guard", "ungrounded", "H_G1a"),
             ("grounded_guard", "grounded_noguard", "H_G1b"),
             ("grounded_noguard", "ungrounded", "H_G1a_aux")]
    g1, holm_input = {}, {}
    for cfg_a, cfg_b, tag in pairs:
        a, b = paired_arrays(ref_cells, cfg_a, cfg_b)
        if len(a) == 0:
            g1[tag] = {"note": f"eşleşen hücre yok ({cfg_a} vs {cfg_b})"}
            continue
        w = wilcoxon_pair(a, b)
        g1[tag] = {"pair": f"{cfg_a} vs {cfg_b}",
                   "gfs_mean": {cfg_a: float(a.mean()), cfg_b: float(b.mean())},
                   "wilcoxon": w,
                   "mcnemar_clean": mcnemar_exact((a == 1).astype(int),
                                                  (b == 1).astype(int)),
                   "bootstrap": bootstrap_diff_ci(a, b)}
        if w.get("p") is not None:
            holm_input[tag] = w["p"]
    for tag, adj in holm(holm_input).items():
        g1[tag]["wilcoxon"]["p_holm"] = adj
    for tag in g1:                      # A21-E1: başarılan eşli n her testte raporlanır
        if "wilcoxon" in g1[tag]:
            g1[tag]["achieved_n"] = g1[tag]["wilcoxon"]["n"]
    rep["G1_reference_gfs"] = g1

    # A21-E1: ÖN-KAYITLI DUYARLILIK — withheld yanıtlar (i) GFS 0 / not-clean
    # (kapsam-cezalı alt sınır), (ii) GFS 1 / clean (fail-closed-kredili üst sınır).
    # Birincil (A2 dışlaması) yukarıda; üçü birlikte raporlanır.
    sens = {}
    for label, fill in (("withheld_as_0", 0.0), ("withheld_as_1", 1.0)):
        recs_s = [dict(r, ref_gfs=fill) if r["withheld"] else r for r in recs]
        cells_s = cell_means(recs_s, "ref_gfs")
        block, hin = {}, {}
        for cfg_a, cfg_b, tag in pairs:
            a, b = paired_arrays(cells_s, cfg_a, cfg_b)
            if len(a) == 0:
                continue
            w = wilcoxon_pair(a, b)
            block[tag] = {"gfs_mean": {cfg_a: float(a.mean()), cfg_b: float(b.mean())},
                          "achieved_n": len(a), "wilcoxon": w,
                          "mcnemar_clean": mcnemar_exact((a == 1).astype(int),
                                                         (b == 1).astype(int)),
                          "bootstrap": bootstrap_diff_ci(a, b)}
            if w.get("p") is not None:
                hin[tag] = w["p"]
        for tag, adj in holm(hin).items():
            block[tag]["wilcoxon"]["p_holm"] = adj
        sens[label] = block
    rep["G1_reference_gfs_sensitivity"] = sens

    # A21-E1 betimsel: over-blocking maliyeti — noguard'da tam-temiz, guard'da withheld
    gg_w = [r for r in recs if r["config"] == "grounded_guard"]
    ng_cells = {q: v for (q, c), v in ref_cells.items() if c == "grounded_noguard"}
    wq_any = {r["qid"] for r in gg_w if r["withheld"]}
    wq_all = {q for q in wq_any
              if all(r["withheld"] for r in gg_w if r["qid"] == q)}
    clean_ng = {q for q, v in ng_cells.items() if v == 1}
    n_q = len({r["qid"] for r in gg_w})
    rep["withheld"] = {
        "n_guard_responses": len(gg_w),
        "n_withheld": sum(r["withheld"] for r in gg_w),
        "withheld_rate": round(sum(r["withheld"] for r in gg_w) / len(gg_w), 4) if gg_w else None,
        "clean_in_noguard_withheld_in_guard": {
            "any_repeat": {"n_questions": len(clean_ng & wq_any),
                           "share_of_questions": round(len(clean_ng & wq_any) / n_q, 4) if n_q else None},
            "all_repeats": {"n_questions": len(clean_ng & wq_all),
                            "share_of_questions": round(len(clean_ng & wq_all) / n_q, 4) if n_q else None},
        },
    }

    # H_G1b ikincil: pre-intervention GFS (iki grounded kolda)
    pre_cells = cell_means(recs, "pre_gfs")
    a, b = paired_arrays(pre_cells, "grounded_guard", "grounded_noguard")
    rep["G1b_pre_intervention"] = (
        {"gfs_mean": {"grounded_guard": float(a.mean()),
                      "grounded_noguard": float(b.mean())},
         "wilcoxon": wilcoxon_pair(a, b),
         "note": "fark ≈0 beklenir → kazanım müdahaleden (dürüst ayrıştırma)"}
        if len(a) else {"note": "veri yok"})

    # H_G2 — zincir uzunluğu etkisi. ANALİZ BİRİMİ = SORU (hücre-ortalaması):
    # tekrarlar önce soru-başına ortalanır → n = soru sayısı (27/19/10), tekrar-
    # düzeyi pseudoreplication YOK (F7-1). Birincil metrik in-run, ikincil referans.
    def _g2(metric: str) -> dict | None:
        ng = [r for r in recs if r["config"] == "grounded_noguard"]
        cell: dict = {}                # qid → tekrar-ortalaması
        for r in ng:
            if r[metric] is not None:
                cell.setdefault(r["qid"], []).append(r[metric])
        cell_gfs = {q: float(np.mean(v)) for q, v in cell.items()}
        qid_chain = {r["qid"]: r["chain"] for r in ng}
        chains = sorted({qid_chain[q] for q in cell_gfs})
        groups = {}
        for c in chains:
            vals = [cell_gfs[q] for q in cell_gfs if qid_chain[q] == c]
            if vals:
                groups[f"chain{c}"] = np.array(vals)
        if len(groups) < 2:
            return None
        kw = stats.kruskal(*groups.values())
        xs = np.array([qid_chain[q] for q in cell_gfs])       # soru-düzeyi
        ys = np.array([cell_gfs[q] for q in cell_gfs])
        rho = stats.spearmanr(xs, ys)
        return {
            "analysis_unit": "question (cell-mean over repeats)",
            "group_means": {k: round(float(v.mean()), 4) for k, v in groups.items()},
            "group_n": {k: int(len(v)) for k, v in groups.items()},   # = 27/19/10
            "kruskal": {"H": float(kw.statistic), "p": float(kw.pvalue)},
            "dunn": dunn_posthoc(groups),
            "spearman": {"rho": float(rho.statistic), "p": float(rho.pvalue)},
        }

    g2 = _g2("inrun_gfs")
    if g2:
        g2["claim_count_covariate_note"] = \
            "chain≥2 sorular doğal olarak daha çok iddia içerir (prereg §6.3)"
        rep["G2_inrun_primary"] = g2
    g2_ref = _g2("ref_gfs")
    if g2_ref:
        rep["G2_reference_secondary"] = g2_ref

    # Guard yan-metrikleri (over-blocking, prereg §3) — grounded_guard kolu
    gg = [r for r in recs if r["config"] == "grounded_guard"]
    if gg:
        rep["guard_side_metrics"] = {
            "n": len(gg),
            "blocked_rate": round(sum(r["blocked"] for r in gg) / len(gg), 4),
            "retried_rate": round(sum(r["retried"] for r in gg) / len(gg), 4),
            "ambiguous_per_response": round(
                float(np.mean([r["ambiguous"] for r in gg])), 3),
        }
        # A21 (betimsel): değerlendirme kapsamı ve blok oranının araç-kullanımına göre kırılımı
        ev = [r for r in gg if r["evaluated"]]
        tl = [r for r in gg if r["toolless"]]
        tool = [r for r in ev if not r["toolless"]]
        rep["guard_side_metrics"].update({
            "evaluated_rate": round(len(ev) / len(gg), 4),
            "toolless_rate": round(len(tl) / len(gg), 4),
            "blocked_rate_toolless": (round(sum(r["blocked"] for r in tl) / len(tl), 4)
                                      if tl else None),
            "blocked_rate_tool": (round(sum(r["blocked"] for r in tool) / len(tool), 4)
                                  if tool else None),
            "withheld_no_claims_rate": round(
                sum(r["ref_gfs"] is None for r in gg) / len(gg), 4),
        })
    return rep


def pooled_sensitivity(recs: list[dict]) -> dict:
    """DUYARLILIK (prereg §6.2): 6-testlik havuzlanmış Holm ailesi = 3 kol çifti
    × 2 model. Her (model, çift) için ayrı Wilcoxon; 6 p-değeri üzerinde Holm.
    BİRİNCİL analiz DEĞİLDİR (o model-içidir); daha muhafazakâr kontrol."""
    by_cells = cell_means(recs, "ref_gfs", by_model=True)   # (model,qid,config)→mean
    models = sorted({m for (m, _, _) in by_cells})
    pairs = [("grounded_guard", "ungrounded", "H_G1a"),
             ("grounded_guard", "grounded_noguard", "H_G1b"),
             ("grounded_noguard", "ungrounded", "H_G1a_aux")]
    raw_p, detail = {}, {}
    for m in models:
        for cfg_a, cfg_b, tag in pairs:
            qids = sorted({q for (mm, q, c) in by_cells if mm == m and c == cfg_a} &
                          {q for (mm, q, c) in by_cells if mm == m and c == cfg_b})
            if not qids:
                continue
            a = np.array([by_cells[(m, q, cfg_a)] for q in qids])
            b = np.array([by_cells[(m, q, cfg_b)] for q in qids])
            w = wilcoxon_pair(a, b)
            key = f"{m}:{tag}"
            detail[key] = {"pair": f"{cfg_a} vs {cfg_b}", "n": w["n"],
                           "gfs_mean": {cfg_a: round(float(a.mean()), 4),
                                        cfg_b: round(float(b.mean()), 4)},
                           "wilcoxon_p": w.get("p")}
            if w.get("p") is not None:
                raw_p[key] = w["p"]
    for key, adj in holm(raw_p).items():
        detail[key]["p_holm_pooled6"] = adj
    return {"note": "SENSITIVITY only — 6-test pooled Holm (3 pairs × 2 models); "
                    "primary is within-model (§6.2)",
            "models": models, "tests": detail}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+", help="raw_g1_*.jsonl dosyaları")
    ap.add_argument("--pooled-sensitivity", action="store_true",
                    help="6-test havuzlanmış Holm duyarlılığı (iki modelin dosyaları)")
    a = ap.parse_args()
    rows = load_rows([Path(p) for p in a.paths])
    recs, excl = extract(rows)
    models = sorted({r["model"] for r in recs if r.get("model")})

    if a.pooled_sensitivity:
        report = {"mode": "pooled_sensitivity", "models": models,
                  "pooled_sensitivity": pooled_sensitivity(recs)}
    else:
        # F7-2: BİRİNCİL analiz TEK model ister (prereg §7) — modeller karışamaz
        if len(models) != 1:
            sys.exit(f"HATA: birincil analiz tek-model ister; girdide modeller={models}. "
                     f"Model başına ayrı çağır veya --pooled-sensitivity kullan.")
        report = analyze_one_model(recs, excl, models[0])

    json.dump(report, sys.stdout, ensure_ascii=False, indent=1)
    print()
