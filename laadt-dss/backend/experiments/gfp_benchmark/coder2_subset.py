"""A29 (taslak) — Kodlayıcı-2 alt-kümesi çekimi [PRE-OUTCOME; kodlayıcı-2'nin ilerlemesi ve hiçbir
etiket bilinmeden, 2026-11-05].

Kodlayıcı-2'nin zamanı tüm öğeleri çift kodlamaya yetmediği için, güvenilirlik (κ) ölçümü sabit tohumla
çekilen bir alt kümede yapılır. Çekim donmuş örneklem tabakalarına göre orantılıdır (en büyük kalan):
  A22-2: tabaka = yol × koşul (`audit/audit_key.csv`, audit_sample.py ile aynı tabakalar)
  A26  : tabaka = S1/S2/S3   (`a26/coding_key.csv`)
Her tabaka içinde öğeler SEED ile karıştırılır; boyut k için tabaka başına ilk n_s öğe alınır.
Anahtar dosyaları yalnız okunur; HİÇBİR tabaka/yol/koşul bilgisi yazdırılmaz ya da dosyaya yazılmaz.
Çıktı `coder2_subset.json`: aday boyutlar için yalnız sıralı öğe kimlikleri.
Kullanım: GFP_RUN_DIR=oct_v42 python -m experiments.gfp_benchmark.coder2_subset
"""
from __future__ import annotations

import csv
import json
import os
import random
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUN = HERE / "results" / os.environ.get("GFP_RUN_DIR", "oct_v42")
SEED = 20261105
SIZES = {"a22": [30, 43], "a26": [80, 100, 132]}


def _strata(path: Path, id_col: str, cols: list[str]) -> dict[str, list[str]]:
    strata: dict[str, set[str]] = defaultdict(set)
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            strata["|".join(row[c] for c in cols)].add(row[id_col])
    return {k: sorted(v) for k, v in strata.items()}


def _draw(strata: dict[str, list[str]], sizes: list[int], rng: random.Random) -> dict[str, list[str]]:
    order = {k: rng.sample(v, len(v)) for k, v in sorted(strata.items())}
    total = sum(len(v) for v in order.values())
    out = {}
    for k in sizes:
        quota = {s: k * len(v) / total for s, v in order.items()}
        alloc = {s: int(q) for s, q in quota.items()}
        for s in sorted(quota, key=lambda s: (-(quota[s] - alloc[s]), s))[: k - sum(alloc.values())]:
            alloc[s] += 1
        out[str(k)] = sorted(i for s, v in order.items() for i in v[: alloc[s]])
        assert len(out[str(k)]) == k
    return out


def main() -> None:
    rng = random.Random(SEED)
    a22 = _strata(RUN / "audit" / "audit_key.csv", "item", ["path", "condition"])
    a26 = _strata(RUN / "a26" / "coding_key.csv", "item_id", ["stratum"])
    res = {"seed": SEED, "run": RUN.name,
           "n_total": {"a22": sum(map(len, a22.values())), "a26": sum(map(len, a26.values()))},
           "a22": _draw(a22, SIZES["a22"], rng), "a26": _draw(a26, SIZES["a26"], rng)}
    for task in ("a22", "a26"):                      # küçük boyut büyüğün alt kümesi mi (bilgi)
        ks = SIZES[task]
        res.setdefault("nested", {})[task] = all(
            set(res[task][str(a)]) <= set(res[task][str(b)]) for a, b in zip(ks, ks[1:]))
    (HERE / "coder2_subset.json").write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8", newline="\n")
    print("n_total", res["n_total"], "sizes", SIZES, "nested", res["nested"])


if __name__ == "__main__":
    main()
