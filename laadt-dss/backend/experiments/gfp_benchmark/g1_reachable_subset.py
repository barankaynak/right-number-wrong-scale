"""Beyan (2026-11-05) B3 — G1 referans-GFS birincil analizlerinin 30-soru duyarlılığı.

Donmuş `compute_gfs` (load_rows → extract → analyze_one_model) aynen çağrılır. Fark yalnız girdi:
soru kimliği aşağıdaki 26 soruya ait satırlar çıkarılır (QUESTION_INPUTS.md: 25 "not fully
reachable" + dis-11, yalnız trafo-erteleme soran). Yazıldı ve hash'lendi: G1 sonuçları
incelenmeden ÖNCE. Model–dil koşulu başına ayrı çağrı (compute_gfs tek-model kuralı).
Kullanım: GFP_RUN_DIR=oct_v42 python -m experiments.gfp_benchmark.g1_reachable_subset
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from experiments.gfp_benchmark.compute_gfs import analyze_one_model, extract, load_rows
from experiments.gfp_benchmark.rescore_crosslingual import FILE_GLOBS, _latest

HERE = Path(__file__).resolve().parent
RUN = HERE / "results" / os.environ.get("GFP_RUN_DIR", "oct_v42")
NOT_REACHABLE = ["res-04", "res-08", "res-10", "res-11", "res-12", "com-05", "com-10", "com-11",
                 "com-14", "dis-03", "dis-05", "dis-09", "dis-10", "dis-13", "sta-01", "sta-02",
                 "sta-03", "sta-05", "sta-06", "sta-07", "sta-08", "sta-09", "sta-10", "sta-11",
                 "sta-12"]
OUTPUT_NOT_PRODUCED_ONLY = ["dis-11"]
EXCLUDED = set(NOT_REACHABLE) | set(OUTPUT_NOT_PRODUCED_ONLY)


def main() -> None:
    qs = json.loads((HERE / "questions.json").read_text(encoding="utf-8"))["questions"]
    keep = sorted(q["id"] for q in qs if q["id"] not in EXCLUDED)
    assert len(NOT_REACHABLE) == 25 and len(keep) == 30 and EXCLUDED <= {q["id"] for q in qs}
    report = {"subset": keep, "excluded": sorted(EXCLUDED), "by_condition": {}}
    for (lang, model), pattern in FILE_GLOBS.items():
        f = _latest(pattern)
        if not f:
            report["by_condition"][f"{lang}|{model}"] = {"status": "no file"}
            continue
        rows = [r for r in load_rows([f]) if (r.get("question") or {}).get("id") in keep]
        recs, excl = extract(rows)
        models = sorted({r["model"] for r in recs if r.get("model")})
        if len(models) != 1:
            report["by_condition"][f"{lang}|{model}"] = {"status": f"models={models}"}
            continue
        report["by_condition"][f"{lang}|{model}"] = {"file": f.name,
                                                     **analyze_one_model(recs, excl, models[0])}
    out = RUN / "g1_reachable_subset.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"-> {out}")


if __name__ == "__main__":
    main()
