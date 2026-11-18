"""B4 — iki kodlayıcının sayfalarından güvenilirlik + kalite metrikleri (A17 donmuş plan).

Girdi (varsayılan): `B4_coding_coder1.csv` (kodlayıcı-1), `B4_coding_coder2.csv`
(kodlayıcı-2) — B4_coding_sheet.csv'nin doldurulmuş kopyaları, item_id ile eşleşir.
Ek: `B4_guard_key.csv` (kategori/set kırılımı + guard×valid çapraz tablosu).
CLI: `compute_b4_kappa.py [coder1.csv coder2.csv]`

PREREGISTRATION §9 / A17'de dondurulan analizler:
 1. Cohen's κ (fluent + category_correct ayrı) + ham anlaşma.
 2. Geçerli-öğe oranı (kodlayıcı-başı + konsensüs) Wilson %95 GA; kategori + set kırılımı.
 4. İkincil/betimsel: valid-altkümede GFP vs legacy recall (Wilson GA zorunlu).
 5. Triangülasyon: insan valid-rate (scale) vs otomatik atıl-analiz.
 κ-duyarlılık üçlüsü: (a) ham, (b) konsensüs (adjudike edilmemişse AND-kuralı),
 (c) yalnız-iki-kodlayıcı-hemfikir alt-küme.

Çıktı: stdout + `B4_results.json` (SHA-256 ile).

Kullanım: python -m experiments.gfp_benchmark.b4_mutation_quality.compute_b4_kappa
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
GUARD_KEY = HERE / "B4_guard_key.csv"
OUT = HERE / "B4_results.json"

VARS = ("fluent_YN", "category_correct_YN")


def _yn(v):
    s = (v or "").strip().upper()
    if s in ("Y", "YES", "E", "EVET", "1", "TRUE"):
        return 1
    if s in ("N", "NO", "H", "HAYIR", "0", "FALSE"):
        return 0
    return None


def _read(path: Path) -> dict[str, dict]:
    if not path.exists():
        raise SystemExit(f"Eksik: {path.name}. İki kodlayıcı da kendi kopyasını doldurmalı.")
    return {r["item_id"]: r for r in csv.DictReader(path.open(encoding="utf-8-sig"))}


def cohen_kappa(pairs):
    n = len(pairs)
    if n == 0:
        return None
    po = sum(1 for a, b in pairs if a == b) / n
    pa1 = sum(a for a, _ in pairs) / n
    pb1 = sum(b for _, b in pairs) / n
    pe = pa1 * pb1 + (1 - pa1) * (1 - pb1)
    if pe == 1.0:
        return 1.0 if po == 1.0 else 0.0
    return (po - pe) / (1 - pe)


def wilson(k, n):
    if n == 0:
        return (0.0, 0.0, 0.0)
    z = 1.959963984540054
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (round(p, 3), round(max(0.0, center - half), 3), round(min(1.0, center + half), 3))


def _valid(row):
    f, c = _yn(row.get("fluent_YN")), _yn(row.get("category_correct_YN"))
    if f is None or c is None:
        return None
    return 1 if (f and c) else 0


def main() -> None:
    args = sys.argv[1:]
    c1 = Path(args[0]) if args else HERE / "B4_coding_coder1.csv"
    c2 = Path(args[1]) if len(args) > 1 else HERE / "B4_coding_coder2.csv"
    A, B = _read(c1), _read(c2)
    ids = sorted(set(A) & set(B))
    if not ids:
        raise SystemExit("İki sayfada ortak item_id yok.")
    if set(A) != set(B):
        print(f"UYARI: item_id kümeleri farklı (A={len(A)}, B={len(B)}, ortak={len(ids)})")
    key = {r["item_id"]: r for r in csv.DictReader(GUARD_KEY.open(encoding="utf-8-sig"))} \
        if GUARD_KEY.exists() else {}
    res = {"coder1": c1.name, "coder2": c2.name, "n_items": len(ids)}

    print(f"== B4 güvenilirlik ({len(ids)} öğe, 2 kodlayıcı: {c1.stem}, {c2.stem}) ==\n")
    res["reliability"] = {}
    for var in VARS:
        pairs = [(_yn(A[i].get(var)), _yn(B[i].get(var))) for i in ids]
        skipped = sum(1 for a, b in pairs if a is None or b is None)
        pairs = [(a, b) for a, b in pairs if a is not None and b is not None]
        k = cohen_kappa(pairs)
        po = sum(1 for a, b in pairs if a == b) / len(pairs) if pairs else 0.0
        # 2x2
        cell = Counter(pairs)
        res["reliability"][var] = {"kappa": k, "raw_agreement": po, "n": len(pairs),
                                   "skipped": skipped,
                                   "cells": {"YY": cell[(1, 1)], "YN": cell[(1, 0)],
                                             "NY": cell[(0, 1)], "NN": cell[(0, 0)]}}
        # A18: anlaşmazlık-YAPISI betimi (güvenilirlik-kurtarma DEĞİL) —
        # marjinal-homojenlik exact testi (discordant b, c üzerinde iki-yönlü binom).
        b, c = cell[(1, 0)], cell[(0, 1)]
        n_d = b + c
        p_mh = min(1.0, 2.0 * sum(math.comb(n_d, i) for i in range(min(b, c) + 1)) * 0.5 ** n_d) \
            if n_d else 1.0
        # Kayıt-amaçlı (MAKALEDE KURTARMA-SAVUNMASI OLARAK KULLANILMAZ — v2.20.3):
        pa1 = sum(a for a, _ in pairs) / len(pairs)
        pb1 = sum(x for _, x in pairs) / len(pairs)
        pi = (pa1 + pb1) / 2
        pe_g = 2 * pi * (1 - pi)
        ac1 = (po - pe_g) / (1 - pe_g) if pe_g != 1 else 0.0
        pabak = 2 * po - 1
        res["reliability"][var].update({"marginal_homogeneity_p": p_mh,
                                        "gwet_ac1": ac1, "pabak": pabak})
        note = f"  ({skipped} boş/geçersiz atlandı)" if skipped else ""
        print(f"{var}:  Cohen's κ = {k:.3f}  |  ham anlaşma = {po:.1%}  |  n={len(pairs)}"
              f"  [A=Y/B=Y {cell[(1,1)]}, A=Y/B=N {cell[(1,0)]}, "
              f"A=N/B=Y {cell[(0,1)]}, A=N/B=N {cell[(0,0)]}]{note}")
        print(f"    tek-yönlülük (marjinal-homojenlik, exact b={b} c={c}): p={p_mh:.2e}"
              f"   [kayıt: Gwet AC1={ac1:+.3f}, PABAK={pabak:+.3f} — KURTARMA-SAVUNMASI DEĞİL]")

    # ---- valid_item: kodlayıcı-başı, AND-konsensüs, hemfikir-altküme ----
    vA = {i: _valid(A[i]) for i in ids}
    vB = {i: _valid(B[i]) for i in ids}
    agree = [i for i in ids if vA[i] is not None and vA[i] == vB[i]]
    cons = {i: (1 if (vA[i] and vB[i]) else 0) for i in ids
            if vA[i] is not None and vB[i] is not None}   # AND = KATI alt-sınır
    lax = {i: (1 if (vA[i] or vB[i]) else 0) for i in ids
           if vA[i] is not None and vB[i] is not None}    # OR  = GEVŞEK üst-sınır

    print("\n== Geçerli-öğe oranı (valid = fluent AND category_correct) ==")
    res["valid_rate"] = {}
    for name, d, sub in ((f"Kodlayıcı-1 ({c1.stem})", vA, ids),
                         (f"Kodlayıcı-2 ({c2.stem})", vB, ids),
                         ("KATI sınır (iki-kodlayıcı AND)", cons, list(cons)),
                         ("GEVŞEK sınır (iki-kodlayıcı OR)", lax, list(lax)),
                         ("Hemfikir-altküme (duyarlılık)", vA, agree)):
        vs = [d[i] for i in sub if d.get(i) is not None]
        p, lo, hi = wilson(sum(vs), len(vs))
        res["valid_rate"][name] = {"k": sum(vs), "n": len(vs), "p": p, "ci95": [lo, hi]}
        print(f"  {name}: {sum(vs)}/{len(vs)} = {p:.1%}  Wilson95 [{lo:.1%}, {hi:.1%}]")

    # ---- kategori / set kırılımı (konsensüs) ----
    if key:
        for label, field in (("Kategori", "category"), ("Set", "set")):
            print(f"\n== {label} kırılımı (konsensüs valid) ==")
            tot, yes = Counter(), Counter()
            for i in cons:
                g = key.get(i, {}).get(field, "?")
                tot[g] += 1
                yes[g] += cons[i]
            bd = {}
            for g in sorted(tot):
                p, lo, hi = wilson(yes[g], tot[g])
                bd[g] = {"k": yes[g], "n": tot[g], "p": p, "ci95": [lo, hi]}
                print(f"  {g:26} {yes[g]}/{tot[g]} = {p:5.1%}  Wilson95 [{lo:.1%}, {hi:.1%}]")
            res[f"by_{field}"] = bd

        # ---- A17-4: valid-altkümede GFP vs legacy recall ----
        print("\n== A17-4 (İKİNCİL/BETİMSEL): geçerli-öğe alt-kümesinde tespit ==")
        subsets = [
            ("KATI valid (AND)", [i for i in cons if cons[i] == 1]),
            ("K1 valid", [i for i in ids if vA[i] == 1]),
            ("K2 valid", [i for i in ids if vB[i] == 1]),
            ("GEVŞEK valid (OR)", [i for i in lax if lax[i] == 1]),
            ("KATI invalid", [i for i in cons if cons[i] == 0]),
            ("TÜMÜ (ITT)", list(ids)),
        ]
        for lbl, sub in subsets:
            g = sum(1 for i in sub if key[i]["gfp_ref_detected"].strip().lower() in ("true", "1"))
            l = sum(1 for i in sub if key[i]["legacy_primary_detected"].strip().lower() in ("true", "1"))
            pg, glo, ghi = wilson(g, len(sub))
            pl, llo, lhi = wilson(l, len(sub))
            print(f"  {lbl:20} n={len(sub):3}  GFP {g:3}/{len(sub):<3} = {pg:5.1%} [{glo:.1%},{ghi:.1%}]"
                  f"   legacy {l:3}/{len(sub):<3} = {pl:5.1%} [{llo:.1%},{lhi:.1%}]")
            res.setdefault("detection", {})[lbl] = {
                "n": len(sub), "gfp": g, "gfp_p": pg, "gfp_ci95": [glo, ghi],
                "legacy": l, "legacy_p": pl, "legacy_ci95": [llo, lhi]}
        print("  (Birincil H_G4 ITT per-kategori McNemar'dır; bu tablo betimseldir — A17-3.)")

    # ---- A18: KONSENSÜS bloku (adjudikasyon sonrası; ön-kayıtlı nokta-değer) ----
    cons_csv = HERE / "B4_consensus.csv"
    if cons_csv.exists() and key:
        CN = {r["item_id"]: r for r in csv.DictReader(cons_csv.open(encoding="utf-8-sig"))}
        vC = {i: _valid(CN[i]) for i in ids if i in CN}
        src = Counter(CN[i].get("source", "?") for i in ids if i in CN)
        print(f"\n{'='*66}\n== KONSENSÜS (A18; adjudике {src['adjudicated']}, hemfikir {src['agreed']}) ==")
        vs = [v for v in vC.values() if v is not None]
        p, lo, hi = wilson(sum(vs), len(vs))
        res["consensus"] = {"source": dict(src), "valid": {"k": sum(vs), "n": len(vs),
                                                           "p": p, "ci95": [lo, hi]}}
        print(f"  Geçerli-öğe oranı: {sum(vs)}/{len(vs)} = {p:.1%}  Wilson95 [{lo:.1%}, {hi:.1%}]"
              f"   (katı sınır {sum(1 for x in vA.values() if x)}/{len(ids)},"
              f" gevşek {sum(1 for x in vB.values() if x)}/{len(ids)})")
        for label, field in (("Kategori", "category"), ("Set", "set")):
            tot, yes = Counter(), Counter()
            for i, v in vC.items():
                if v is None:
                    continue
                g = key.get(i, {}).get(field, "?")
                tot[g] += 1
                yes[g] += v
            bd = {}
            print(f"  -- {label} kırılımı --")
            for g in sorted(tot):
                pp, l2, h2 = wilson(yes[g], tot[g])
                bd[g] = {"k": yes[g], "n": tot[g], "p": pp, "ci95": [l2, h2]}
                print(f"     {g:26} {yes[g]}/{tot[g]} = {pp:5.1%}  [{l2:.1%}, {h2:.1%}]")
            res["consensus"][f"by_{field}"] = bd
        print("  -- Tespit (A17-4; birincil H_G4 DEĞİL, betimsel) --")
        for lbl, sub in (("konsensüs-GEÇERLİ", [i for i, v in vC.items() if v == 1]),
                         ("konsensüs-geçersiz", [i for i, v in vC.items() if v == 0])):
            g = sum(1 for i in sub if key[i]["gfp_ref_detected"].strip().lower() in ("true", "1"))
            l = sum(1 for i in sub if key[i]["legacy_primary_detected"].strip().lower() in ("true", "1"))
            pg, g1, g2 = wilson(g, len(sub))
            pl, l1, l2 = wilson(l, len(sub))
            res["consensus"].setdefault("detection", {})[lbl] = {
                "n": len(sub), "gfp": g, "gfp_p": pg, "gfp_ci95": [g1, g2],
                "legacy": l, "legacy_p": pl, "legacy_ci95": [l1, l2]}
            print(f"     {lbl:20} n={len(sub):3}  GFP {g:3}/{len(sub):<3} = {pg:5.1%} [{g1:.1%},{g2:.1%}]"
                  f"   legacy {l:3}/{len(sub):<3} = {pl:5.1%} [{l1:.1%},{l2:.1%}]")

    # ---- adjudikasyon listesi ----
    dis = [i for i in ids if vA[i] != vB[i]]
    res["disagreements"] = dis
    print(f"\n== Adjudikasyon gereken (valid_item farkı): {len(dis)} öğe ==")
    for i in dis:
        print(f"  {i} [{key.get(i,{}).get('category','?')}] "
              f"K1 f={A[i].get('fluent_YN','').strip()} c={A[i].get('category_correct_YN','').strip()} | "
              f"K2 f={B[i].get('fluent_YN','').strip()} c={B[i].get('category_correct_YN','').strip()}")

    js = json.dumps(res, ensure_ascii=False, indent=1)
    OUT.write_text(js, encoding="utf-8")
    print(f"\n-> {OUT.name}  SHA-256 {hashlib.sha256(js.encode()).hexdigest()[:16]}…")


if __name__ == "__main__":
    main()
