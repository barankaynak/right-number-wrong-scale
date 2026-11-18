"""A22-1 — Müdahale-yolu tabakalaşması [PRE-RUN, prereg-v3.1]. LLM'siz.

grounded_guard kolundaki provenance'lı her yanıt tam olarak bir yola düşer:
    P0   retried=False                                   (müdahale yok)
    P1a  retried ∧ ¬blocked ∧ teslimde ≥1 skorlanan iddia (düzeltmeyle çözüldü)
    P1b  retried ∧ ¬blocked ∧ teslimde skorlanan iddia yok (düzeltme sayısız; E1 withheld)
    P2   blocked ∧ n_records>0 ∧ özette ≥1 skorlanan iddia (provenance özetiyle alıkonuldu)
    P3   blocked ∧ (n_records=0 ∨ özette skorlanan iddia yok)  (sayısız alıkonuldu)
"Skorlanan iddia" teslim metninin referans-grafa karşı (`reference_check.counts`) IGNORED
dışı iddiasıdır. Eşleştirme: aynı (qid, tekrar) grounded_noguard yanıtı (ilk taslak
kol-bağımsız olduğundan P0'ın Δ'ya katkısı tanım gereği 0'dır).

Koşul başına: yol payları; yol başına teslim referans-GFS ortalaması, tam-temiz oranı,
eşli noguard referans-GFS'i ve yol-içi Δ; ayrıştırma Δ = Σ pay × Δ_yol (birincil: tanımlı
çiftler; E1 varyantları: P1b/P3 teslim GFS'i 0 ya da 1 doldurulur); P1a/P2 için ilk taslak
vs teslim referans-GFS'i yan yana (A10 karşı-olgusalı); P2'de referans-GFS<1 özet sayısı;
düzeltmeyle-çözülme payı |P1a∪P1b|/|retried| ve E3 kırılımı. Sonuç-koşulsuz raporlanır.

Kullanım: GFP_RUN_DIR=oct_v42 python -m experiments.gfp_benchmark.intervention_paths
"""
from __future__ import annotations

import json
import statistics
from collections import defaultdict

from experiments.gfp_benchmark.rescore_crosslingual import FILE_GLOBS, _latest, _gfs
from experiments.gfp_benchmark.run_benchmark import RESULTS
from experiments.gfp_benchmark.run_g4_final import _ref_graph_and_results

SCORED = ("GROUNDED", "UNGROUNDED", "SCALE_VIOLATION", "UNIT_MISMATCH")
PATHS = ("P0", "P1a", "P1b", "P2", "P3")


def _n_scored(counts: dict | None) -> int:
    return sum((counts or {}).get(k, 0) for k in SCORED)


def classify(rec: dict) -> str | None:
    prov = rec.get("provenance")
    if prov is None:
        return None
    delivered_scored = _n_scored((rec.get("reference_check") or {}).get("counts")) > 0
    if not prov.get("retried"):
        return "P0"
    if not prov.get("blocked"):
        return "P1a" if delivered_scored else "P1b"
    if prov.get("n_records", 0) > 0 and delivered_scored:
        return "P2"
    return "P3"


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return statistics.mean(xs) if xs else None


def main() -> None:
    from app.llm import ollama_orchestrator as oo
    orch = oo.OllamaOrchestrator()
    ref_cache: dict = {}

    def ref_graph(q):
        if q["id"] not in ref_cache:
            ref_cache[q["id"]] = _ref_graph_and_results(q, orch)[0]
        return ref_cache[q["id"]]

    out = {}
    for (lang, model), pattern in FILE_GLOBS.items():
        f = _latest(pattern)
        if not f:
            continue
        rows = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
        rows = [r for r in rows if not r.get("fallback") and not r.get("error")]
        noguard = {(r["question"]["id"], r.get("repeat")): r for r in rows
                   if r["config"] == "grounded_noguard"}
        by_path = defaultdict(list)
        e3 = defaultdict(int)
        retried = 0
        for r in rows:
            if r["config"] != "grounded_guard":
                continue
            path = classify(r)
            if path is None:
                continue
            prov = r["provenance"]
            if prov.get("retried"):
                retried += 1
                if prov.get("retry_tool_calls_requested"):
                    e3["retry_requested_tool"] += 1
                elif prov.get("retry_error") or prov.get("retry_content_empty"):
                    e3["retry_empty_or_error"] += 1
                else:
                    e3["retry_restated_numbers"] += 1
            delivered = _gfs((r.get("reference_check") or {}).get("counts") or {})
            ng = noguard.get((r["question"]["id"], r.get("repeat")))
            ng_gfs = _gfs((ng.get("reference_check") or {}).get("counts") or {}) if ng else None
            first_draft = None
            if path in ("P1a", "P2"):
                pre = ((prov.get("pre_intervention") or {}).get("reply")) or ""
                g = ref_graph(r["question"])
                if g is not None and pre:
                    first_draft = _gfs(g.check_response(pre).counts)
            by_path[path].append({"delivered": delivered, "noguard": ng_gfs,
                                  "first_draft": first_draft})
        n = sum(len(v) for v in by_path.values())
        cond = {"n_guard_responses": n, "paths": {}, "decomposition": {}}
        for p in PATHS:
            items = by_path.get(p, [])
            pairs = [(i["delivered"], i["noguard"]) for i in items
                     if i["delivered"] is not None and i["noguard"] is not None]
            cond["paths"][p] = {
                "n": len(items), "share": round(len(items) / n, 4) if n else None,
                "delivered_ref_gfs": _mean([i["delivered"] for i in items]),
                "delivered_clean_rate": _mean([float(i["delivered"] == 1.0) for i in items
                                               if i["delivered"] is not None]),
                "paired_noguard_ref_gfs": _mean([b for _, b in pairs]),
                "paired_delta": _mean([a - b for a, b in pairs]),
                "n_pairs": len(pairs),
                "first_draft_ref_gfs": _mean([i["first_draft"] for i in items]),
                "summaries_ref_gfs_below_1": (sum(1 for i in items if i["delivered"] is not None
                                                   and i["delivered"] < 1.0) if p == "P2" else None),
            }
        for label, fill in (("primary", None), ("withheld_as_0", 0.0), ("withheld_as_1", 1.0)):
            total, parts = 0.0, {}
            for p in PATHS:
                deltas = []
                for i in by_path.get(p, []):
                    d = i["delivered"]
                    if d is None and fill is not None and p in ("P1b", "P3"):
                        d = fill
                    if d is not None and i["noguard"] is not None:
                        deltas.append(d - i["noguard"])
                share = len(by_path.get(p, [])) / n if n else 0.0
                contrib = share * statistics.mean(deltas) if deltas else 0.0
                parts[p] = round(contrib, 5)
                total += contrib
            cond["decomposition"][label] = {"sum": round(total, 5), "by_path": parts}
        resolved = len(by_path.get("P1a", [])) + len(by_path.get("P1b", []))
        cond["correction_resolution_share"] = round(resolved / retried, 4) if retried else None
        cond["e3_breakdown_retried"] = dict(e3)
        out[f"{lang}|{model}"] = cond
        print(lang, model, {p: cond["paths"][p]["n"] for p in PATHS},
              "decomp", cond["decomposition"]["primary"]["sum"])
    (RESULTS / "intervention_paths.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("-> intervention_paths.json")


if __name__ == "__main__":
    main()
