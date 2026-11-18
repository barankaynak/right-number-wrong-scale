"""A22-2 insan izlenebilirlik-denetimi analizi (AUDIT_CODEBOOK.md "Pre-registered analyses" + A29-2).

Yazıldı ve hash'lendi: kodlayıcı dosyaları hash'lenmeden ÖNCE (A29-5). Kodlayıcı-1 tüm 86 yanıtı,
kodlayıcı-2 yalnız `coder2_subset.json` boyut "30" alt kümesini kodladı.

Birimler: sayı = (item, number ≥ 1); yanıt = item. `traceable_YN` ∈ {Y, N, N/A}.
- κ (Cohen) iki kodlayıcının örtüşmesinde:
    sayı düzeyi  — `traceable_YN`, N/A dışlanır: iki kodlayıcıdan biri N/A dediyse birim κ'ya girmez
                   (N/A uyuşmazlıkları ayrıca sayılır);
    yanıt düzeyi — `usable_answer_YN`.
  Her biriyle ham uyum ve PABAK (= 2·po − 1) raporlanır.
- Y1 = matcher GROUNDED dediği sayılarda insan-Y payı; Y2 = matcher ihlal (UNGROUNDED,
  SCALE_VIOLATION, UNIT_MISMATCH) dediği sayılarda insan-Y payı. İnsan N/A paydadan dışlanır.
  Wilson %95 GA; yol başına ve toplam. Usable-oranı yol başına.
- Birincil etiket = kodlayıcı-1 (86). Örtüşmede kodlayıcı-1, kodlayıcı-2, katı (AND) ve gevşek (OR)
  etiketlerle aynı ölçütler yan yana (A18 sınırları, her zaman raporlanır).
Kullanım: GFP_RUN_DIR=oct_v42 python -m experiments.gfp_benchmark.a22_audit_analysis
"""
from __future__ import annotations

import csv
import json
import os
from collections import Counter, defaultdict
from pathlib import Path

from experiments.gfp_benchmark.scale_assertion_analysis import _kappa, _wilson

HERE = Path(__file__).resolve().parent
RUN = HERE / "results" / os.environ.get("GFP_RUN_DIR", "oct_v42")
KEY = RUN / "audit" / "audit_key.csv"
C1 = RUN / "coded" / "audit_coded_coder1.csv"
C2 = RUN / "coded" / "audit_coded_coder2.csv"
SUBSET = HERE / "coder2_subset.json"
OUT = RUN / "audit" / "a22_results.json"
VIOLATIONS = ("UNGROUNDED", "SCALE_VIOLATION", "UNIT_MISMATCH")
PATHS = ("P0", "P1a", "P2")


def _read(path: Path) -> tuple[dict, dict]:
    """→ (sayı etiketleri {(item, n): Y|N|N/A}, yanıt etiketleri {item: Y|N})."""
    nums, usable = {}, {}
    for r in csv.DictReader(path.open(encoding="utf-8-sig", newline="")):
        item, n = r["item"].strip(), int(r["number"])
        if item not in usable:                         # yanıt etiketi öğenin ilk satırında
            usable[item] = r["usable_answer_YN"].strip().upper()
        if n >= 1:
            t = r["traceable_YN"].strip().upper()
            nums[(item, n)] = "N/A" if t in ("N/A", "NA") else t
    bad = [k for k, v in nums.items() if v not in ("Y", "N", "N/A")] + \
          [k for k, v in usable.items() if v not in ("Y", "N")]
    if bad:
        raise SystemExit(f"{path.name}: {len(bad)} geçersiz/eksik etiket (ilk: {bad[:5]})")
    return nums, usable


def _pabak(k: dict) -> float | None:
    return None if k.get("raw_agreement") is None else round(2 * k["raw_agreement"] - 1, 4)


def _share(units: list, lab: dict) -> dict:
    ys = [lab[u] for u in units if lab.get(u) in ("Y", "N")]
    k = sum(v == "Y" for v in ys)
    return {"k": k, "n": len(ys), "share": round(k / len(ys), 4) if ys else None,
            "wilson95": _wilson(k, len(ys)), "n_NA_excluded": sum(lab.get(u) == "N/A" for u in units)}


def _block(items: set, key: dict, path_of: dict, nums: dict, usable: dict) -> dict:
    out = {}
    for p in PATHS + ("all",):
        its = {i for i in items if p == "all" or path_of[i] == p}
        g = [u for u, v in key.items() if u[0] in its and v == "GROUNDED"]
        viol = [u for u, v in key.items() if u[0] in its and v in VIOLATIONS]
        us = [usable[i] for i in its]
        out[p] = {"n_responses": len(its), "Y1": _share(g, nums), "Y2": _share(viol, nums),
                  "usable": {"k": us.count("Y"), "n": len(us),
                             "share": round(us.count("Y") / len(us), 4) if us else None,
                             "wilson95": _wilson(us.count("Y"), len(us))}}
    return out


def main() -> None:
    key, path_of, verdicts = {}, {}, Counter()
    for r in csv.DictReader(KEY.open(encoding="utf-8-sig", newline="")):
        path_of[r["item"]] = r["path"]
        if int(r["number"]) >= 1:
            key[(r["item"], int(r["number"]))] = r["matcher_verdict"]
            verdicts[r["matcher_verdict"]] += 1
    sub = set(json.loads(SUBSET.read_text(encoding="utf-8"))["a22"]["30"])
    n1, u1 = _read(C1)
    n2, u2 = _read(C2)
    all_items = set(path_of)
    assert set(u1) == all_items and set(n1) == set(key), "kodlayıcı-1 dosyası anahtarla örtüşmüyor"
    assert set(u2) == sub and set(n2) == {u for u in key if u[0] in sub}, "kodlayıcı-2 alt kümesi uyuşmuyor"

    ov_units = sorted(u for u in key if u[0] in sub)
    na_disagree = sum((n1[u] == "N/A") != (n2[u] == "N/A") for u in ov_units)
    k_num = _kappa([n1[u] for u in ov_units if "N/A" not in (n1[u], n2[u])],
                   [n2[u] for u in ov_units if "N/A" not in (n1[u], n2[u])])
    k_use = _kappa([u1[i] for i in sorted(sub)], [u2[i] for i in sorted(sub)])
    echo = Counter()
    for r in csv.DictReader(C1.open(encoding="utf-8-sig", newline="")):
        if int(r["number"]) >= 1 and key.get((r["item"], int(r["number"]))) == "GROUNDED" \
                and r["traceable_YN"].strip().upper() == "Y":
            echo["input_echo" if r["input_echo"].strip().upper() == "Y" else "sheet"] += 1

    # A18 sınırları: ikisi de N/A → N/A; katı Y yalnız ikisi de Y; gevşek Y biri Y; kalan N
    strict_n = {u: "N/A" if n1[u] == n2[u] == "N/A" else "Y" if n1[u] == n2[u] == "Y" else "N"
                for u in ov_units}
    lenient_n = {u: "N/A" if n1[u] == n2[u] == "N/A" else "Y" if "Y" in (n1[u], n2[u]) else "N"
                 for u in ov_units}
    strict_u = {i: "Y" if u1[i] == u2[i] == "Y" else "N" for i in sub}
    lenient_u = {i: "Y" if "Y" in (u1[i], u2[i]) else "N" for i in sub}

    res = {
        "design": "A29: coder-1 all 86 (primary); coder-2 seed-drawn subset of 30 (reliability)",
        "n": {"responses": len(all_items), "numbers": len(key), "overlap_responses": len(sub),
              "overlap_numbers": len(ov_units)},
        "matcher_verdicts_all": dict(verdicts),
        "reliability_overlap": {
            "number_level_traceable": {**k_num, "pabak": _pabak(k_num), "NA_excluded_rule":
                                       "unit dropped if either coder marked N/A",
                                       "NA_disagreements": na_disagree},
            "response_level_usable": {**k_use, "pabak": _pabak(k_use)}},
        "primary_coder1_all": _block(all_items, key, path_of, n1, u1),
        "primary_input_echo_in_Y1_numerator": dict(echo),
        "overlap": {"coder1": _block(sub, key, path_of, n1, u1),
                    "coder2": _block(sub, key, path_of, n2, u2),
                    "strict_AND": _block(sub, key, path_of, strict_n, strict_u),
                    "lenient_OR": _block(sub, key, path_of, lenient_n, lenient_u)},
    }
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
