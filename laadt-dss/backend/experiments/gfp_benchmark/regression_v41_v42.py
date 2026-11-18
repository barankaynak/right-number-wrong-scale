"""Guard v4.1 → v4.2 regresyon kanıtı (A21).

v4.2 yalnız BOŞ-graf yolunu değiştirir (araç çağrılmamış tek-tur). Bu script Temmuz
korpusundaki HER metni — 5 koşulun G1 yanıtları (pre_intervention + teslim) ve 3 G4
setinin kaynak/mutasyon metinleri — aynı kol-bağımsız referans grafa karşı hem v4.1
(git `prereg` hash'li dosya) hem v4.2 ile skorlar ve iddia-düzeyinde karşılaştırır.
Referans graflar boş değildir → beklenen fark SIFIR. Fark varsa G4/B4 v4.2 altında
Temmuz verisiyle tutulamaz.

Kullanım: python -m experiments.gfp_benchmark.regression_v41_v42 <v41_guard.py>
"""
from __future__ import annotations

import glob
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

from experiments.gfp_benchmark.rescore_crosslingual import FILE_GLOBS, _latest
from experiments.gfp_benchmark.run_g4_final import _ref_graph_and_results
from experiments.gfp_benchmark.run_benchmark import RESULTS

G4_GLOBS = ("raw_g4_final_seed42_*.jsonl", "raw_g4_final_en_seed42_*.jsonl",
            "raw_g4_final_mistral-small3.2-24b_seed42_*.jsonl")


def _load_v41(path: str):
    spec = importlib.util.spec_from_file_location("provenance_guard_v41", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["provenance_guard_v41"] = mod
    spec.loader.exec_module(mod)
    return mod


def _sig(rep) -> list:
    return [(c.text, c.value, c.verdict, c.matched_key, c.record_scale,
             tuple(c.claimed_scales)) for c in rep.claims]


def main() -> None:
    v41_path = sys.argv[1]
    v41 = _load_v41(v41_path)
    from app.llm import ollama_orchestrator as oo
    orch = oo.OllamaOrchestrator()

    graphs: dict = {}

    def pair(q):
        if q["id"] not in graphs:
            g42 = _ref_graph_and_results(q, orch)[0]
            g41 = None
            if g42 is not None:
                g41 = v41.ProvenanceGraph()
                g41.load_records(g42.records_as_dicts())
            graphs[q["id"]] = (g41, g42)
        return graphs[q["id"]]

    n_texts = n_claims = 0
    diffs = []

    def compare(q, text, where):
        nonlocal n_texts, n_claims
        if not text:
            return
        g41, g42 = pair(q)
        if g42 is None:
            return
        a, b = _sig(g41.check_response(text)), _sig(g42.check_response(text))
        n_texts += 1
        n_claims += len(b)
        if a != b:
            diffs.append({"where": where, "qid": q["id"], "v41": a, "v42": b})

    for (lang, model), pattern in FILE_GLOBS.items():
        f = _latest(pattern)
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            q = rec["question"]
            pre = ((rec.get("provenance") or {}).get("pre_intervention") or {}).get("reply")
            compare(q, pre, f"g1:{f.name}")
            compare(q, rec.get("reply"), f"g1:{f.name}")

    qs = {q["id"]: q for q in json.loads(
        (RESULTS.parent / "questions.json").read_text(encoding="utf-8"))["questions"]}
    for pat in G4_GLOBS:
        for fn in sorted(glob.glob(str(RESULTS / pat))):
            for line in Path(fn).read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                rec = json.loads(line)
                q = qs.get(rec.get("qid"))
                if q is None:
                    continue
                for fld in ("source", "mutated"):
                    compare(q, rec.get(fld), f"g4:{Path(fn).name}")

    v42_path = Path(oo.__file__).with_name("provenance_guard.py")
    out = {
        "v41_sha256": hashlib.sha256(Path(v41_path).read_bytes()).hexdigest(),
        "v42_sha256": hashlib.sha256(v42_path.read_bytes()).hexdigest(),
        "texts_compared": n_texts, "claims_compared": n_claims,
        "n_diffs": len(diffs), "diffs": diffs[:50],
    }
    (RESULTS / "regression_v41_v42.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k != "diffs"}, indent=1))


if __name__ == "__main__":
    main()
