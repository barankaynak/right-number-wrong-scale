"""A30 — EVREN keşifsel koşusunun analizi [PRE-RUN; hash'i A30 kaydında]. Betimsel; doğrulayıcı
iddia yok. Donmuş analizler DEĞİŞTİRİLMEDEN çağrılır; değişen yalnız girdi:
  1) `compute_gfs.analyze_one_model` (CLI ile aynı yol) → a30_gfs.json
  2) `rescore_crosslingual`, `intervention_paths`, `trap_analysis`, `g1_reachable_subset` `main()`:
     paylaşılan `FILE_GLOBS` sözlüğü yerinde tek EVREN koşuluna indirgenir; çıktılar her
     betiğin kendi dosya adıyla GFP_RUN_DIR (oct_v42_evren) altına yazılır, Ekim dosyalarına değil.
  3) G1-MT: donmuş `multiturn_analysis.analyze`, MT_RUN = bu dizin, G1_RUN = oct_v42 (vekil
     doğrulaması Ekim'den okunur) → mt_results.json
  4) determinizm: DET_QIDS 5 hücresi, ana koşunun aynı seed'li (10000) grounded_noguard satırıyla:
     teslim metni birebir aynı mı, referans-GFS farkı
  5) çağrı telemetrisi (a30_calls.jsonl): çağrı/kapasite-bekleme sayısı, token toplamları,
     sunulan model adları, finish_reason dağılımı
Referans grafları simülasyon motorunu çağırır (2, 3) — koşudan sonra, motor boşken çalıştırılır.
Kullanım: GFP_RUN_DIR=oct_v42_evren python -m experiments.gfp_benchmark.a30_analysis
"""
from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path

from experiments.gfp_benchmark import rescore_crosslingual as rc
from experiments.gfp_benchmark.compute_gfs import analyze_one_model, extract, gfs_from_counts, load_rows
from experiments.gfp_benchmark.run_a30_evren import LANG, MODELS
from experiments.gfp_benchmark.run_benchmark import RESULTS
from experiments.gfp_benchmark.run_g1_rerun import DET_QIDS

HERE = Path(__file__).resolve().parent
assert os.environ.get("GFP_RUN_DIR") and RESULTS.name != "oct_v42", "GFP_RUN_DIR=oct_v42_evren gerekli"


def _pattern(model: str) -> str:
    return f"raw_g1_{model.replace(':', '-')}_2026*T*.jsonl"


def _jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def main() -> None:
    report: dict = {"models": MODELS, "lang": LANG}
    # 1) birincil G1 analizi, model başına
    report["gfs"] = {}
    for m in MODELS:
        f = rc._latest(_pattern(m))
        if not f:
            report["gfs"][m] = {"status": "not run"}
            continue
        recs, excl = extract(load_rows([f]))
        report["gfs"][m] = {"file": f.name, **analyze_one_model(recs, excl, m)}
    (RESULTS / "a30_gfs.json").write_text(
        json.dumps(report["gfs"], ensure_ascii=False, indent=1, default=str), encoding="utf-8")

    # 2) donmuş ikincil analizler, tek EVREN koşuluna indirgenmiş FILE_GLOBS ile
    rc.FILE_GLOBS.clear()
    rc.FILE_GLOBS.update({(LANG, m): _pattern(m) for m in MODELS})
    rc.MODELS_BY_LANG.clear()
    rc.MODELS_BY_LANG[LANG] = list(MODELS)
    from experiments.gfp_benchmark import g1_reachable_subset, intervention_paths, trap_analysis
    for name, fn in (("rescore", rc.main), ("paths", intervention_paths.main),
                     ("trap", trap_analysis.main), ("reach30", g1_reachable_subset.main)):
        try:
            fn()
            report.setdefault("secondary_ok", []).append(name)
        except Exception as exc:                      # biri çökerse diğerleri yine koşar
            report.setdefault("secondary_failed", {})[name] = repr(exc)

    # 3) G1-MT
    from experiments.gfp_benchmark import multiturn_analysis as mta
    mta.MT_RUN, mta.G1_RUN = RESULTS, HERE / "results" / "oct_v42"
    report["mt"] = "mt_results.json" if list(RESULTS.glob("raw_mt_*.jsonl")) else "not run"
    if report["mt"] != "not run":
        mta.analyze()

    # 4) determinizm
    report["determinism"] = {}
    for m in MODELS:
        main_f = rc._latest(_pattern(m))
        dets = sorted(RESULTS.glob(f"determinism_check_{m.replace(':', '-')}_*.jsonl"))
        if not (main_f and dets):
            continue
        base = {r["question"]["id"]: r for r in _jsonl(main_f)
                if r["config"] == "grounded_noguard" and r["repeat"] == 0}
        cells = []
        for d in _jsonl(dets[-1]):
            b = base.get(d["question"]["id"])
            if not b:
                continue
            g = [gfs_from_counts((r.get("reference_check") or {}).get("counts")) for r in (d, b)]
            cells.append({"qid": d["question"]["id"], "reply_identical": d.get("reply") == b.get("reply"),
                          "ref_gfs_det": g[0], "ref_gfs_main": g[1]})
        report["determinism"][m] = {"n": len(cells),
                                    "reply_identical": sum(c["reply_identical"] for c in cells),
                                    "cells": cells}

    # 5) çağrı telemetrisi
    calls = RESULTS / "a30_calls.jsonl"
    if calls.exists():
        ev = _jsonl(calls)
        c = [e for e in ev if e["event"] == "call"]
        report["telemetry"] = {
            "calls": len(c), "capacity_wait_events": sum(e["event"] == "capacity_wait" for e in ev),
            "served_models": dict(Counter(e.get("served_model") for e in c)),
            "finish_reason": dict(Counter(e.get("finish_reason") for e in c)),
            "prompt_tokens": sum((e.get("usage") or {}).get("prompt_tokens", 0) for e in c),
            "completion_tokens": sum((e.get("usage") or {}).get("completion_tokens", 0) for e in c),
            "had_reasoning": sum(bool(e.get("had_reasoning")) for e in c)}

    out = RESULTS / "a30_results.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str) + "\n",
                   encoding="utf-8")
    print(f"-> {out}")


if __name__ == "__main__":
    main()
