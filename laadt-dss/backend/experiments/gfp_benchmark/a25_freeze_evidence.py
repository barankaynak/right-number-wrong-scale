"""A25 — Jev doğrulayıcı için evidence + öğe dosyasını tag'den ÖNCE dondurur (clear-sky replay).

Çıktı: results/a25_evidence_items.json — her G4 seti için:
  evidence[qid] = {"raw": <metin>, "annotated": <metin>}
    raw       : her araç adımı için araç adı + girdi argümanları + JSON çıktı; ölçek etiketi YOK
                (beyan: JSON anahtarları birim taşır, araç adı ölçeği ima eder)
    annotated : kayıt başına anahtar, değer, birim, ölçek (building/feeder/policy), kaynak fonksiyon
  items: her enjeksiyon için {id, set, qid, category, original_sentence, mutated_sentence}
         (mutasyonun değiştirdiği cümle; mutasyonsuz orijinal ile eşli); her kontrol için
         {id, set, qid, kind: control, sentences: [sayı içeren cümleler]}
Backend'e ve Redis'e yazılmaz (süreç-içi clear-sky). Jev çağrıları `jev_g4.py` ile, tag sonrası.

Kullanım: python -m experiments.gfp_benchmark.a25_freeze_evidence
"""
from __future__ import annotations

import hashlib
import json
import re

from experiments.gfp_benchmark import clearsky_mode
from experiments.gfp_benchmark.a23_legacy_decomposition import G4_SETS
from experiments.gfp_benchmark.run_benchmark import HERE

RESULTS = HERE / "results"
_DROP = {"irradiance_source", "tmy_sha256"}          # A23 sonrası alanlar; Temmuz çıktısında yoktu
_NUM = re.compile(r"\d")


def _raw(steps: list) -> str:
    parts = []
    for i, (tool, args, result) in enumerate(steps, 1):
        res = {k: v for k, v in result.items() if k not in _DROP}
        parts.append(f"Tool call {i}: {tool}\nArguments: {json.dumps(args, ensure_ascii=False)}\n"
                     f"Output: {json.dumps(res, ensure_ascii=False)}")
    return "\n\n".join(parts)


def _annotated(graph) -> str:
    lines = ["Simulator records (key | value | unit | valid scale | source function):"]
    for d in graph.records_as_dicts():
        if isinstance(d.get("value"), (int, float)):
            lines.append(f"{d['key']} | {d['value']} | {d.get('unit') or '-'} | "
                         f"{d.get('scale')} | {d.get('source_function')}")
    return "\n".join(lines)


def _changed_sentence(src: str, mut: str):
    from app.llm.provenance_guard import _split_sentences
    a, b = _split_sentences(src), _split_sentences(mut)
    if len(a) != len(b):
        return None
    diffs = [(x, y) for x, y in zip(a, b) if x != y]
    return diffs[0] if len(diffs) == 1 else None


def main() -> None:
    clearsky_mode.enable()
    from app.llm import ollama_orchestrator as oo
    from app.llm.provenance_guard import _split_sentences
    from experiments.gfp_benchmark.run_benchmark import _resolve_prev_refs, _stk
    orch = oo.OllamaOrchestrator()
    qs = {q["id"]: q for q in json.loads((HERE / "questions.json").read_text(
        encoding="utf-8"))["questions"]}

    from app.llm.provenance_guard import ProvenanceGraph
    evidence, items, skipped = {}, [], []
    for name, fn in G4_SETS.items():
        rows = [json.loads(l) for l in (RESULTS / fn).read_text(encoding="utf-8").splitlines()
                if l.strip()]
        for r in rows:
            qid = r["qid"]
            if qid not in evidence:
                q = qs[qid]
                stk, per_step = _stk(q["stakeholder"]), q.get("suggested_args_per_step")
                g, steps, prior = ProvenanceGraph(), [], []
                for i, tool in enumerate(q.get("expected_tools", [])):
                    raw_args = dict((per_step[i] if per_step and i < len(per_step)
                                     else q.get("suggested_args")) or {})
                    raw_args.pop("stakeholder_type", None)
                    args = _resolve_prev_refs(raw_args, prior)
                    res = orch._execute_tool(tool, args, stk)
                    g.add_tool_result(tool, args, stk, res)
                    steps.append((tool, args, res))
                    prior.append(res)
                evidence[qid] = {"raw": _raw(steps), "annotated": _annotated(g)}
            if r["kind"] == "control":
                sents = [s for s in _split_sentences(r["source"]) if _NUM.search(s)]
                items.append({"id": f"{name}-ctrl-{qid}", "set": name, "qid": qid,
                              "kind": "control", "sentences": sents})
                continue
            pair = _changed_sentence(r["source"], r["mutated"])
            if pair is None:
                skipped.append({"set": name, "qid": qid, "category": r["category"]})
                continue
            items.append({"id": f"{name}-{len(items):04d}", "set": name, "qid": qid,
                          "kind": "injected", "category": r["category"],
                          "original_sentence": pair[0], "mutated_sentence": pair[1]})
    payload = {"evidence": evidence, "items": items, "skipped_unpairable": skipped,
               "irradiance": "clearsky replay (A23-3)"}
    js = json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True)
    path = RESULTS / "a25_evidence_items.json"
    path.write_text(js, encoding="utf-8")
    n_inj = sum(i["kind"] == "injected" for i in items)
    print(f"{len(evidence)} qid evidence, {n_inj} enjeksiyon öğesi, "
          f"{len(items) - n_inj} kontrol, {len(skipped)} eşlenemeyen -> {path.name} "
          f"sha256 {hashlib.sha256(js.encode()).hexdigest()}")


if __name__ == "__main__":
    main()
