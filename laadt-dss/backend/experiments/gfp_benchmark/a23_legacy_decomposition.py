"""A23-4 — G4 legacy (değer-eşleştirme guard) uyarı-kanalı ayrıştırması
[EXPLORATORY, POST-OUTCOME, sonuç-koşulsuz]. LLM'siz; Temmuz G4 korpusu, clear-sky replay.

Her G4 kaydı (enjeksiyon ve kontrol) için legacy `validate_response` uyarıları türlerine
ayrılır: (i) özgül-verim fiziksel-sınır uyarısı ("Özgül verim …"; PV clear-sky arızasıyla
tetiklenebilecek tek uyarı türü), (ii) sayısal-sapma uyarısı ("… büyük sapma"), (iii) diğer.
S1 (violation ∪ son-araç uyarıları) ve S2 (herhangi bir aracın ihlal/uyarısı) kontrol-FP'si
ve enjeksiyon recall'ü "artefakt dahil / hariç" iki sütunla raporlanır.

Kullanım: python -m experiments.gfp_benchmark.a23_legacy_decomposition
"""
from __future__ import annotations

import glob
import json
from collections import Counter, defaultdict
from pathlib import Path

from experiments.gfp_benchmark import clearsky_mode
from experiments.gfp_benchmark.run_benchmark import HERE

RESULTS = HERE / "results"
# Makalede raporlanan üç G4 seti (g4_summary.json / crosslingual_stats.json kaynakları)
# TR: otoriter 109'luk dosya (…011118Z) metin saklamaz; metin-taşıyan seed-42 yeniden-üretimi
# 97/109 (PREREGISTRATION B4 "metin otantikliği" notu; B4 de bu dosyadan örnekledi).
G4_SETS = {"tr": "raw_g4_final_seed42_20260710T074242Z.jsonl",            # 97 + 36 (metinli)
           "en": "raw_g4_final_en_seed42_20260710T190205Z.jsonl",         # 87 + 38
           "mistral": "raw_g4_final_mistral-small3.2-24b_seed42_20260710T225730Z.jsonl"}  # 66 + 28
SETS = G4_SETS


def _wtype(w: str) -> str:
    if w.startswith("Özgül verim"):
        return "specific_yield"
    if "büyük sapma" in w:
        return "numeric_deviation"
    return "other"


def _readings(text, results, drop_yield: bool):
    from app.llm.hallucination_guard import validate_response

    def flags(res):
        vr = validate_response(text, res)
        ws = [w for w in vr.warnings if not (drop_yield and _wtype(w) == "specific_yield")]
        return (not vr.passed), ws, vr.warnings

    last = results[-1] if results else None
    p, ws_last, all_last = flags(last)
    s1 = p or bool(ws_last)
    s2 = False
    for res in results:
        pv, ws, _ = flags(res)
        s2 = s2 or pv or bool(ws)
    return p, s1, s2, all_last


def main() -> None:
    clearsky_mode.enable()
    from app.llm import ollama_orchestrator as oo
    from experiments.gfp_benchmark.run_g4_final import _ref_graph_and_results
    orch = oo.OllamaOrchestrator()
    qs = {q["id"]: q for q in json.loads((HERE / "questions.json").read_text(
        encoding="utf-8"))["questions"]}
    cache: dict = {}
    out = {}
    for name, pat in SETS.items():
        fs = sorted(glob.glob(str(RESULTS / pat)))
        if not fs:
            continue
        rows = [json.loads(l) for l in Path(fs[-1]).read_text(encoding="utf-8").splitlines()
                if l.strip()]
        agg = defaultdict(lambda: defaultdict(int))
        wtypes = Counter()
        for r in rows:
            q = qs.get(r["qid"])
            if q is None:
                continue
            if r["qid"] not in cache:
                cache[r["qid"]] = _ref_graph_and_results(q, orch)[1] or []
            results = cache[r["qid"]]
            kind = r["kind"]
            for drop in (False, True):
                p, s1, s2, all_last = _readings(r["mutated"], results, drop)
                tag = "excl_yield" if drop else "incl_yield"
                a = agg[f"{kind}|{tag}"]
                a["n"] += 1
                a["primary"] += int(p)
                a["s1"] += int(s1)
                a["s2"] += int(s2)
                if not drop:
                    wtypes.update(_wtype(w) for w in all_last)
            # tutarlılık: incl_yield okuması saklı Temmuz bayraklarını yeniden üretmeli
            p, s1, s2, _ = _readings(r["mutated"], results, False)
            agg[f"{kind}|replay_check"]["n"] += 1
            agg[f"{kind}|replay_check"]["s1_matches_stored"] += int(
                s1 == bool(r.get("legacy_s1_warn_detected")))
            agg[f"{kind}|replay_check"]["s2_matches_stored"] += int(
                s2 == bool(r.get("legacy_s2_ceiling_detected")))
        out[name] = {"readings": {k: dict(v) for k, v in agg.items()},
                     "warning_types_last_tool": dict(wtypes)}
        print(name, json.dumps(out[name]["readings"], ensure_ascii=False))
    (RESULTS / "a23_legacy_decomposition.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("-> a23_legacy_decomposition.json")


if __name__ == "__main__":
    main()
