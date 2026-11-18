"""Cross-lingual + 3-model istatistikleri (offline; rescore çıktısından + EN G4 raw'dan).

Girdi: `results/crosslingual_cells.json` (per-soru hücre-ort referans-GFS, lang|model|arm)
       + en yeni `raw_g4_final_en_seed42_*.jsonl`.

Testler:
 1) H_LANG-1 (cross-lingual G1): TR vs EN eşleştirilmiş Wilcoxon (grounded_noguard) +
    bootstrap ΔGFS %95 GA (seed=42). null-yönelimli: fark ANLAMSIZ beklenir → dile-dayanıklı.
 2) Manipülasyon-kontrolü (3 model, TR): grounded_noguard vs ungrounded eşleştirilmiş
    Wilcoxon — araç-temellendirme GFS'i artırıyor mu (her modelde).
 3) EN G4: per-kategori exact McNemar (GFP-ref vs legacy-primary) — yapısal körlük EN'de.

Kullanım: python -m experiments.gfp_benchmark.crosslingual_stats
"""
from __future__ import annotations
import glob
import json
import math
import os
import random
from pathlib import Path
from statistics import mean

from scipy.stats import wilcoxon

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"                      # G4 setleri (Temmuz korpusu, A21: korunur)
# A21: G1-türevli hücreler yeniden-koşu alt-dizininden (GFP_RUN_DIR); boşsa Temmuz düzeni
RUN = RESULTS / os.environ.get("GFP_RUN_DIR", "")
CELLS = json.loads((RUN / "crosslingual_cells.json").read_text(encoding="utf-8"))
CATS = ["scale_swap", "unit_swap", "value_fabrication", "small_int_fabrication"]
# A24: model listeleri koşul kümesinden türer (Temmuz: gemma/qwen3.5/mistral; Ekim: güncel küme)
from experiments.gfp_benchmark.rescore_crosslingual import MODELS_BY_LANG  # noqa: E402
BI_MODELS = [m for m in MODELS_BY_LANG.get("tr", []) if m in MODELS_BY_LANG.get("en", [])]
TR_MODELS = list(MODELS_BY_LANG.get("tr", []))
# Beyan 2026-11-05 (koşu-sonrası hata düzeltmesi): koşulmamış koşul (hücresi yok) atlanır;
# verisi olan modellerin hesabı değişmez. Ekim'de glm-4.7-flash "not run" (iki deneme iptal).
_HAS = lambda lang, m: any(k.startswith(f"{lang}|{m}|") and CELLS[k] for k in CELLS)
NOT_RUN = sorted({m for m in TR_MODELS if not _HAS("tr", m)} | {m for m in BI_MODELS if not _HAS("en", m)})
BI_MODELS = [m for m in BI_MODELS if _HAS("tr", m) and _HAS("en", m)]
TR_MODELS = [m for m in TR_MODELS if _HAS("tr", m)]
if NOT_RUN:
    print(f"not run (no cells): {NOT_RUN}")


def paired(a_key, b_key):
    A, B = CELLS.get(a_key, {}), CELLS.get(b_key, {})
    qids = sorted(set(A) & set(B))
    xs = [A[q] for q in qids]
    ys = [B[q] for q in qids]
    return qids, xs, ys, [x - y for x, y in zip(xs, ys)]


def wilcox_p(diffs):
    nz = [d for d in diffs if d != 0]
    if not nz:
        return None
    try:
        return float(wilcoxon(nz).pvalue)
    except Exception:
        return None


def boot_ci(diffs, n=10000, seed=42):
    rng = random.Random(seed)
    k = len(diffs)
    if k == 0:
        return (float("nan"), float("nan"))
    ms = []
    for _ in range(n):
        s = 0.0
        for _ in range(k):
            s += diffs[rng.randrange(k)]
        ms.append(s / k)
    ms.sort()
    return (ms[int(0.025 * n)], ms[int(0.975 * n)])


def mcnemar_exact(b, c):
    """İki-yönlü exact binom McNemar (discordant b, c)."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    p = 2.0 * sum(math.comb(n, i) for i in range(k + 1)) * (0.5 ** n)
    return min(1.0, p)


print("=" * 70)
print("1) H_LANG-1 — cross-lingual G1 (TR vs EN, grounded_noguard, eşleştirilmiş)")
print("   null-yönelimli: fark ANLAMSIZ → grounding dile-dayanıklı")
print("-" * 70)
for m in BI_MODELS:
    # EN önce → diffs = EN - TR (pozitif = İngilizce daha grounded)
    qids, en_xs, tr_ys, diffs = paired(f"en|{m}|grounded_noguard", f"tr|{m}|grounded_noguard")
    lo, hi = boot_ci(diffs)
    p = wilcox_p(diffs)
    verdict = "n.s. (dile-dayanıklı)" if (p is None or p > 0.05) else "ANLAMLI (dil farkı)"
    print(f"  {m:13} n={len(qids)}  TR={mean(tr_ys):.3f}  EN={mean(en_xs):.3f}  "
          f"Δ(EN-TR)={mean(diffs):+.3f}  CI95[{lo:+.3f},{hi:+.3f}]  "
          f"Wilcoxon p={p if p is None else round(p,4)}  → {verdict}")

print("\n" + "=" * 70)
print("2) Manipülasyon-kontrolü — grounded_noguard > ungrounded (3 model, TR, eşli)")
print("   araç-temellendirme GFS'i artırmalı (her açık-modelde)")
print("-" * 70)
for m in TR_MODELS:
    qids, xs, ys, diffs = paired(f"tr|{m}|grounded_noguard", f"tr|{m}|ungrounded")
    p = wilcox_p(diffs)
    sig = "anlamlı ✓" if (p is not None and p < 0.05) else "n.s."
    print(f"  {m:20} n={len(qids)}  grounded={mean(xs):.3f}  ungrounded={mean(ys):.3f}  "
          f"Δ={mean(diffs):+.3f}  p={p if p is None else round(p,4)}  ({sig})")

print("\n" + "=" * 70)
print("3) EN G4 — per-kategori exact McNemar (GFP-ref vs legacy-primary)")
print("   yapısal körlük: legacy 0 → GFP tespitleri discordant b, c=0")
print("-" * 70)
f = sorted(glob.glob(str(RESULTS / "raw_g4_final_en_seed42_*.jsonl")))[-1]
inj = [json.loads(l) for l in Path(f).read_text(encoding="utf-8").splitlines()
       if l.strip() and json.loads(l)["kind"] == "injected"]
tb = tc = 0
for cat in CATS:
    ci = [r for r in inj if r["category"] == cat]
    b = sum(1 for r in ci if r["gfp_ref_detected"] and not r["legacy_primary_detected"])
    c = sum(1 for r in ci if r["legacy_primary_detected"] and not r["gfp_ref_detected"])
    tb += b
    tc += c
    p = mcnemar_exact(b, c)
    print(f"  {cat:22} GFP {sum(r['gfp_ref_detected'] for r in ci)}/{len(ci)}  "
          f"legacy {sum(r['legacy_primary_detected'] for r in ci)}/{len(ci)}  "
          f"McNemar(b={b},c={c}) p={p:.2e}")
print(f"  {'POOLED':22} b={tb} c={tc}  p={mcnemar_exact(tb, tc):.2e} (betimsel; kategoriler qid paylaşır)")

# ---- persist (V6-v: stdout değil dosya + hash) ----
import hashlib
out = {"h_lang1": {}, "manip": {}, "en_g4": {}}
for m in BI_MODELS:
    q, ex, ty, df = paired(f"en|{m}|grounded_noguard", f"tr|{m}|grounded_noguard")
    lo, hi = boot_ci(df)
    out["h_lang1"][m] = {"n": len(q), "tr": mean(ty), "en": mean(ex),
                         "delta_en_tr": mean(df), "ci95": [lo, hi], "wilcoxon_p": wilcox_p(df)}
for m in TR_MODELS:
    q, xs, ys, df = paired(f"tr|{m}|grounded_noguard", f"tr|{m}|ungrounded")
    out["manip"][m] = {"n": len(q), "grounded": mean(xs), "ungrounded": mean(ys),
                       "delta": mean(df), "wilcoxon_p": wilcox_p(df)}
out["g4_by_set"] = {}   # y1: EN + Mistral G4 recall + KONTROL-FP + per-kat McNemar
for setname, pat in (("en", "raw_g4_final_en_seed42_*.jsonl"),
                     ("mistral", "raw_g4_final_mistral-small3.2-24b_seed42_*.jsonl")):
    fs = sorted(glob.glob(str(RESULTS / pat)))
    if not fs:
        continue
    rows = [json.loads(l) for l in Path(fs[-1]).read_text(encoding="utf-8").splitlines() if l.strip()]
    ij = [r for r in rows if r["kind"] == "injected"]
    ct = [r for r in rows if r["kind"] == "control"]
    cats = {}
    for cat in CATS:
        ci = [r for r in ij if r["category"] == cat]
        b = sum(1 for r in ci if r["gfp_ref_detected"] and not r["legacy_primary_detected"])
        cats[cat] = {"n": len(ci), "gfp": sum(r["gfp_ref_detected"] for r in ci),
                     "legacy": sum(r["legacy_primary_detected"] for r in ci),
                     "mcnemar_p": mcnemar_exact(b, 0)}
    out["g4_by_set"][setname] = {
        "n_inj": len(ij), "gfp_total": sum(r["gfp_ref_detected"] for r in ij),
        "legacy_total": sum(r["legacy_primary_detected"] for r in ij),
        "control_n": len(ct),
        "control_gfp_fp": sum(r["gfp_ref_detected"] for r in ct),
        "control_legacy_viol": sum(r["legacy_primary_detected"] for r in ct),
        "control_legacy_warn": sum(r["legacy_s1_warn_detected"] for r in ct),
        "control_legacy_ceil": sum(r["legacy_s2_ceiling_detected"] for r in ct),
        "per_category": cats}
out["en_g4"] = out["g4_by_set"].get("en", {}).get("per_category", {})
js = json.dumps(out, ensure_ascii=False, indent=1)
p = RUN / "crosslingual_stats.json"
p.write_text(js, encoding="utf-8")
print(f"\n-> {p.name}  SHA-256 {hashlib.sha256(js.encode()).hexdigest()[:16]}…")
