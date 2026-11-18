"""A22-3 — Tolerans duyarlılığı (§4-104, §7.1-7 ön-kayıtlı; ilk kez raporlanır). LLM'siz.

`app.llm.provenance_guard._REL_TOL` ∈ {0.01, 0.02, 0.05} (+ 0.0, "A22'de eklendi" sınırı)
çalışma-anında değiştirilir; donmuş guard dosyası DEĞİŞMEZ. Kademeli mutlak tabanlar (0.01 ve
0.5) SABİT kalır; legacy guard'ın kendi toleransı taranmaz (beyan). Zorunlu uyarı: guard %2
toleransla MÜDAHALE ETTİ ve yeniden koşulamaz — tarama ölçümü değiştirir, müdahaleyi değil.

Alt komutlar:
  g1        Ekim G1 (GFP_RUN_DIR): model başına referans-GFS kol ortalamaları, H_G1a/H_G1b
            Wilcoxon + bootstrap GA — teslim VE ilk-taslak metni.
  g4        Temmuz G4 korpusu (clear-sky replay): kategori başına GFP recall + kontrol-FP.
  taxonomy  Ekim taksonomisinin tolerans-tanımlı "value matches reference" kategori payı.

Kullanım: [GFP_RUN_DIR=oct_v42] python -m experiments.gfp_benchmark.tolerance_sensitivity g1|g4|taxonomy
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np

TOLS = (0.0, 0.01, 0.02, 0.05)
# Yalnız mekanik duman-testi için (A22-8d): dosya başına ilk N satır. Raporlanan koşuda BOŞ.
_SMOKE = int(os.environ.get("GFP_SMOKE_LIMIT", "0")) or None


def _set_tol(tol: float) -> None:
    import app.llm.provenance_guard as pg
    pg._REL_TOL = tol


def g1() -> None:
    from experiments.gfp_benchmark.compute_gfs import (
        bootstrap_diff_ci, cell_means, gfs_from_counts, paired_arrays, wilcoxon_pair)
    from experiments.gfp_benchmark.rescore_crosslingual import FILE_GLOBS, _latest
    from experiments.gfp_benchmark.run_benchmark import RESULTS
    from experiments.gfp_benchmark.run_g4_final import _ref_graph_and_results
    from app.llm import ollama_orchestrator as oo
    orch = oo.OllamaOrchestrator()
    graphs: dict = {}
    out: dict = {}
    for (lang, model), pattern in FILE_GLOBS.items():
        f = _latest(pattern)
        if not f:
            continue
        rows = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
        rows = [r for r in rows if not r.get("fallback") and not r.get("error")][:_SMOKE]
        res_cond: dict = {}
        for tol in TOLS:
            _set_tol(tol)
            per_text: dict = {"delivered": [], "first_draft": []}
            for r in rows:
                q = r["question"]
                if q["id"] not in graphs:
                    graphs[q["id"]] = _ref_graph_and_results(q, orch)[0]
                g = graphs[q["id"]]
                if g is None:
                    continue
                pre = (((r.get("provenance") or {}).get("pre_intervention") or {})
                       .get("reply")) or r.get("reply") or ""
                for label, text in (("delivered", r.get("reply") or ""), ("first_draft", pre)):
                    v = gfs_from_counts(g.check_response(text).counts) if text else None
                    per_text[label].append({"model": model, "qid": q["id"],
                                            "config": r["config"], "ref_gfs": v})
            block: dict = {}
            for label, recs in per_text.items():
                cells = cell_means(recs, "ref_gfs")
                arms = {c: float(np.mean([v for (q, cc), v in cells.items() if cc == c]))
                        for c in ("grounded_guard", "grounded_noguard", "ungrounded")
                        if any(cc == c for (_, cc) in cells)}
                tests = {}
                for a, b, tag in (("grounded_guard", "ungrounded", "H_G1a"),
                                  ("grounded_guard", "grounded_noguard", "H_G1b")):
                    xa, xb = paired_arrays(cells, a, b)
                    if len(xa):
                        tests[tag] = {"n": len(xa), "wilcoxon": wilcoxon_pair(xa, xb),
                                      "bootstrap": bootstrap_diff_ci(xa, xb)}
                block[label] = {"arm_means": arms, "tests": tests}
            res_cond[str(tol)] = block
        out[f"{lang}|{model}"] = res_cond
        print(lang, model, {t: res_cond[t]["delivered"]["arm_means"] for t in res_cond})
    _set_tol(0.02)
    (RESULTS / "tolerance_sensitivity_g1.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


def g4() -> None:
    from experiments.gfp_benchmark import clearsky_mode
    clearsky_mode.enable()
    from experiments.gfp_benchmark.a23_legacy_decomposition import G4_SETS
    from experiments.gfp_benchmark.run_benchmark import HERE
    from experiments.gfp_benchmark.run_g4_final import _ref_graph_and_results
    from app.llm import ollama_orchestrator as oo
    orch = oo.OllamaOrchestrator()
    results_dir = HERE / "results"
    qs = {q["id"]: q for q in json.loads((HERE / "questions.json").read_text(
        encoding="utf-8"))["questions"]}
    graphs: dict = {}
    out: dict = {}
    for name, fn in G4_SETS.items():
        rows = [json.loads(l) for l in (results_dir / fn).read_text(encoding="utf-8").splitlines()
                if l.strip()][:_SMOKE]
        res_set: dict = {}
        for tol in TOLS:
            _set_tol(tol)
            cats: dict = {}
            ctrl = [0, 0]
            for r in rows:
                if r["qid"] not in graphs:
                    graphs[r["qid"]] = _ref_graph_and_results(qs[r["qid"]], orch)[0]
                g = graphs[r["qid"]]
                if g is None:
                    continue
                det = not g.check_response(r["mutated"]).passed
                if r["kind"] == "control":
                    ctrl[0] += 1
                    ctrl[1] += int(det)
                else:
                    c = cats.setdefault(r["category"], [0, 0])
                    c[0] += 1
                    c[1] += int(det)
            res_set[str(tol)] = {"recall": {k: {"n": v[0], "detected": v[1]} for k, v in cats.items()},
                                 "control": {"n": ctrl[0], "fp": ctrl[1]}}
        out[name] = res_set
        print(name, {t: {k: v["detected"] for k, v in res_set[t]["recall"].items()} for t in res_set})
    _set_tol(0.02)
    (results_dir / "tolerance_sensitivity_g4.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


def taxonomy() -> None:
    import experiments.gfp_benchmark.analyze_guard_flag_taxonomy as tax
    from experiments.gfp_benchmark.run_benchmark import RESULTS
    out = {}
    for tol in TOLS:
        _set_tol(tol)
        tax._TOL = tol
        r = tax.run()
        out[str(tol)] = {"n_flags": r["n_flags"], "categories": r["categories"],
                         "category_pct": r["category_pct"]}
        print(tol, out[str(tol)])
    _set_tol(0.02)
    (RESULTS / "tolerance_sensitivity_taxonomy.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    {"g1": g1, "g4": g4, "taxonomy": taxonomy}[sys.argv[1]]()
