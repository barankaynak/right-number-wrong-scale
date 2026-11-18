"""Çapraz-ölçek tuzak-soruları ayrık raporu — A19 [EXPLORATORY, POST-OUTCOME, PRE-ANALYSIS].

7 tuzak sorusu (`scale_focus=="cross"`) vs diğer 49 soru; A15 ile aynı enstrüman:
saklı pre_intervention metinleri TEK guard v4.1 ile kol-bağımsız referans grafa karşı
yeniden-skorlanır (rescore_crosslingual.py ile aynı yükleme/dışlama). LLM koşusu YOK.

Metrikler (PREREGISTRATION §9-A19):
    M1  yanıt başına ≥1 SCALE_VIOLATION — soru-düzeyi ortalama oran (birim = soru-hücresi)
    M2  referans-GFS hücre-ortalaması
    M3  grounded_guard teslim tarafı: in-run blocked/retried + teslim reply'ında SV
    M4  tuzaklarda bayraklanan SV cümleleri dosyaya (insan-doğrulamalı precision İDDİA YOK)
Test: grounded_noguard kolunda M1 için iki-yönlü Mann–Whitney U (7 vs 49), keşifsel.

Kullanım: python -m experiments.gfp_benchmark.trap_analysis
"""
from __future__ import annotations

import json
import statistics
from collections import defaultdict

from scipy import stats

from experiments.gfp_benchmark.rescore_crosslingual import (
    ARMS, FILE_GLOBS, _latest, _pre_reply, _gfs)
from experiments.gfp_benchmark.run_g4_final import _ref_graph_and_results
from experiments.gfp_benchmark.run_benchmark import RESULTS


def _mean(xs):
    return statistics.mean(xs) if xs else None


def main() -> None:
    from app.llm import ollama_orchestrator as oo
    orch = oo.OllamaOrchestrator()

    ref_cache: dict = {}

    def ref_graph(q):
        if q["id"] not in ref_cache:
            ref_cache[q["id"]] = _ref_graph_and_results(q, orch)[0]
        return ref_cache[q["id"]]

    # (lang, model, arm, stratum) -> qid -> [per-response değerler]
    sv_any = defaultdict(lambda: defaultdict(list))
    gfs = defaultdict(lambda: defaultdict(list))
    # M3: (lang, model) -> sayaçlar (yalnız tuzak, grounded_guard)
    m3 = defaultdict(lambda: defaultdict(int))
    flagged = []

    for (lang, model), pattern in FILE_GLOBS.items():
        f = _latest(pattern)
        if not f:
            print(f"UYARI: {lang}/{model} dosyası yok ({pattern})")
            continue
        rows = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
        for rec in rows:
            arm = rec.get("config")
            if arm not in ARMS or rec.get("fallback") or rec.get("error"):
                continue
            q = rec["question"]
            pre = _pre_reply(rec) or rec.get("reply")
            if not pre:
                continue
            g = ref_graph(q)
            if g is None:
                continue
            stratum = "trap" if q.get("scale_focus") == "cross" else "other"
            key = (lang, model, arm, stratum)
            rep = g.check_response(pre)
            n_sv = rep.counts.get("SCALE_VIOLATION", 0)
            sv_any[key][q["id"]].append(1.0 if n_sv > 0 else 0.0)
            gv = _gfs(rep.counts)
            if gv is not None:
                gfs[key][q["id"]].append(gv)

            if stratum != "trap":
                continue
            for c in rep.claims:
                if c.verdict == "SCALE_VIOLATION":
                    flagged.append({
                        "lang": lang, "model": model, "arm": arm, "qid": q["id"],
                        "repeat": rec.get("repeat"), "claim": c.text,
                        "matched_key": c.matched_key, "record_scale": c.record_scale,
                        "claimed_scales": c.claimed_scales, "sentence": c.sentence,
                    })
            if arm == "grounded_guard":
                prov = rec.get("provenance") or {}
                c3 = m3[(lang, model)]
                c3["n"] += 1
                c3["pre_sv"] += int(n_sv > 0)
                c3["blocked"] += int(bool(prov.get("blocked")))
                c3["retried"] += int(bool(prov.get("retried")))
                delivered = rec.get("reply") or ""
                d_sv = g.check_response(delivered).counts.get("SCALE_VIOLATION", 0) if delivered else 0
                c3["delivered_sv"] += int(d_sv > 0)
                c3["pre_sv_and_delivered_sv"] += int(n_sv > 0 and d_sv > 0)

    out: dict = {"conditions": {}, "m3_guard_trap": {}}
    print("=== A19 tuzak vs diğer (guard v4.1, referans-graf, pre_intervention) ===")
    print(f"{'lang':4} {'model':21} {'arm':17} {'M1 trap':>8} {'M1 oth':>7} "
          f"{'M2 trap':>8} {'M2 oth':>7} {'nQ t/o':>7} {'MWU p':>7}")
    for (lang, model) in FILE_GLOBS:
        for arm in ARMS:
            row = {}
            per_q = {}
            for st in ("trap", "other"):
                k = (lang, model, arm, st)
                qm_sv = [statistics.mean(v) for v in sv_any[k].values() if v]
                qm_gfs = [statistics.mean(v) for v in gfs[k].values() if v]
                per_q[st] = qm_sv
                row[st] = {"m1_sv_rate": _mean(qm_sv), "m2_gfs": _mean(qm_gfs),
                           "nQ_sv": len(qm_sv), "nQ_gfs": len(qm_gfs),
                           "n_responses": sum(len(v) for v in sv_any[k].values())}
            p = None
            if arm == "grounded_noguard" and per_q["trap"] and per_q["other"]:
                p = float(stats.mannwhitneyu(per_q["trap"], per_q["other"],
                                             alternative="two-sided").pvalue)
            row["mwu_p_m1"] = p
            out["conditions"][f"{lang}|{model}|{arm}"] = row
            t, o = row["trap"], row["other"]
            fmt = lambda x: f"{x:.3f}" if x is not None else "  -  "
            print(f"{lang:4} {model:21} {arm:17} {fmt(t['m1_sv_rate']):>8} {fmt(o['m1_sv_rate']):>7} "
                  f"{fmt(t['m2_gfs']):>8} {fmt(o['m2_gfs']):>7} "
                  f"{t['nQ_sv']:>3}/{o['nQ_sv']:<3} {fmt(p):>7}")

    print("\n=== M3 grounded_guard, tuzak yanıtları (teslim tarafı) ===")
    for (lang, model), c in m3.items():
        out["m3_guard_trap"][f"{lang}|{model}"] = dict(c)
        print(f"{lang:4} {model:21} n={c['n']:3} pre_SV={c['pre_sv']:3} blocked={c['blocked']:3} "
              f"retried={c['retried']:3} delivered_SV={c['delivered_sv']:3} "
              f"(pre&delivered SV={c['pre_sv_and_delivered_sv']})")

    (RESULTS / "trap_analysis.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    with (RESULTS / "trap_flagged_sentences.jsonl").open("w", encoding="utf-8") as fh:
        for r in flagged:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\n-> trap_analysis.json + trap_flagged_sentences.jsonl ({len(flagged)} SV bayrağı)")


if __name__ == "__main__":
    main()
