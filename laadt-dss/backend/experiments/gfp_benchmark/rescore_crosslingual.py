"""Cross-lingual yeniden-skorlama — TR ve EN G1 yanıtlarını TEK guard (v4.1) ile skorla.

prereg A15 kuralı: nihai cross-lingual metrikler, HER İKİ DİLİN saklı pre_intervention
(guard-öncesi ham LLM) yanıtlarının AYNI guard sürümüyle (v4.1) POST-HOC skorlanmasıyla
hesaplanır → tek-guard, adil karşılaştırma; LLM yeniden-koşusu YOK. G1 birincil metriği =
referans-GFS (grounded / non-ignored), kol-bağımsız tam-zincir referans grafına karşı.

Metrik dil-agnostik parser (v4.1) ile; dil TEK değişen faktör. Referans graf araç
çıktılarından kurulur (LLM üretimi YOK — GPU'suz).

Kullanım: python -m experiments.gfp_benchmark.rescore_crosslingual
"""
from __future__ import annotations
import glob
import json
import os
import statistics
from collections import defaultdict
from pathlib import Path

from experiments.gfp_benchmark.run_g4_final import _ref_graph_and_results
from experiments.gfp_benchmark.run_benchmark import RESULTS

# En son (tam) ham G1 dosyaları — dil × model
# A24: Ekim yeniden-koşusu (GFP_RUN_DIR dolu) güncel model kümesiyle; Temmuz dizini (boş)
# Temmuz kümesini korur → Temmuz analizleri aynen yeniden-üretilebilir.
FILE_GLOBS_OCT = {
    ("tr", "gemma4:e4b"):           "raw_g1_gemma4-e4b_2026*T*.jsonl",
    ("tr", "qwen3.8:27b"):          "raw_g1_qwen3.8-27b_2026*T*.jsonl",
    ("tr", "mistral-small3.2:24b"): "raw_g1_mistral-small3.2-24b_2026*.jsonl",
    ("tr", "glm-4.7-flash:latest"): "raw_g1_glm-4.7-flash-latest_2026*.jsonl",
    ("tr", "muse-glimmer:30b"):     "raw_g1_muse-glimmer-30b_2026*.jsonl",
    ("en", "gemma4:e4b"):           "raw_g1_gemma4-e4b_en_*.jsonl",
    ("en", "qwen3.8:27b"):          "raw_g1_qwen3.8-27b_en_*.jsonl",
}
FILE_GLOBS_JULY = {
    # A21: tarih-bağımsız (Ekim yeniden-koşusu GFP_RUN_DIR alt-dizininde); Temmuz
    # dizininde _latest yine en büyük (tam-koşu) dosyayı seçer → Temmuz çıktısı değişmez
    ("tr", "gemma4:e4b"):   "raw_g1_gemma4-e4b_2026*T*.jsonl",
    ("tr", "qwen3.5:27b"):  "raw_g1_qwen3.5-27b_2026*T*.jsonl",
    ("tr", "mistral-small3.2:24b"): "raw_g1_mistral-small3.2-24b_2026*.jsonl",  # A16 3. model
    ("en", "gemma4:e4b"):   "raw_g1_gemma4-e4b_en_*.jsonl",
    ("en", "qwen3.5:27b"):  "raw_g1_qwen3.5-27b_en_*.jsonl",
}
FILE_GLOBS = FILE_GLOBS_OCT if os.environ.get("GFP_RUN_DIR") else FILE_GLOBS_JULY
ARMS = ("grounded_guard", "grounded_noguard", "ungrounded")
# dile göre mevcut modeller (rapor sırası)
MODELS_BY_LANG = {}
for (_l, _m) in FILE_GLOBS:
    MODELS_BY_LANG.setdefault(_l, [])
    if _m not in MODELS_BY_LANG[_l]:
        MODELS_BY_LANG[_l].append(_m)


def _gfs(counts: dict):
    g = counts.get("GROUNDED", 0)
    denom = g + counts.get("UNGROUNDED", 0) + counts.get("SCALE_VIOLATION", 0) + counts.get("UNIT_MISMATCH", 0)
    return (g / denom) if denom > 0 else None


def _latest(pattern: str) -> Path | None:
    hits = sorted(glob.glob(str(RESULTS / pattern)))
    # TR için: en büyük (tam-koşu) dosya; EN için tek dosya
    if not hits:
        return None
    return max((Path(h) for h in hits), key=lambda p: p.stat().st_size)


def _pre_reply(rec: dict) -> str | None:
    return ((rec.get("provenance") or {}).get("pre_intervention") or {}).get("reply")


def main() -> None:
    from app.llm import ollama_orchestrator as oo
    orch = oo.OllamaOrchestrator()

    ref_cache: dict = {}   # (lang,model,qid) bağımsız — qid'e göre (araç çıktısı dile bağlı değil)

    def ref_graph(q):
        qid = q["id"]
        if qid not in ref_cache:
            g, _ = _ref_graph_and_results(q, orch)
            ref_cache[qid] = g
        return ref_cache[qid]

    # (lang, model, arm) -> [per-cell mean gfs]  (pseudoreplication: hücre = qid, tekrar-ort.)
    cell = defaultdict(lambda: defaultdict(list))   # key -> qid -> [gfs per repeat]
    verdict_sum = defaultdict(lambda: defaultdict(int))  # (lang,model,arm) -> verdict -> toplam
    n_scored = defaultdict(int)
    n_empty = defaultdict(int)

    for (lang, model), pattern in FILE_GLOBS.items():
        f = _latest(pattern)
        if not f:
            print(f"UYARI: {lang}/{model} dosyası yok ({pattern})")
            continue
        rows = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
        for rec in rows:
            if rec.get("config") not in ARMS or rec.get("fallback") or rec.get("error"):
                continue
            reply = _pre_reply(rec) or rec.get("reply")
            key = (lang, model, rec["config"])
            if not reply:
                n_empty[key] += 1
                continue
            g = ref_graph(rec["question"])
            if g is None:
                continue
            rep = g.check_response(reply)
            gv = _gfs(rep.counts)
            for v, c in rep.counts.items():
                verdict_sum[key][v] += c
            n_scored[key] += 1
            if gv is not None:
                cell[key][rec["question"]["id"]].append(gv)

    # ---- rapor ----
    print("=== CROSS-LINGUAL yeniden-skorlama (guard v4.1, pre_intervention referans-GFS) ===\n")
    print(f"{'lang':4} {'model':13} {'arm':17} {'ref-GFS':>8} {'nQ':>4} {'GR':>4} {'UNG':>4} {'SCL':>4} {'UNIT':>4} {'IGN':>5}")
    summary = {}
    for lang in ("tr", "en"):
        for model in MODELS_BY_LANG.get(lang, []):
            for arm in ARMS:
                key = (lang, model, arm)
                qmeans = [statistics.mean(v) for v in cell[key].values() if v]
                gfs = statistics.mean(qmeans) if qmeans else float("nan")
                vs = verdict_sum[key]
                summary[key] = {"gfs": gfs, "nQ": len(qmeans), "verdicts": dict(vs)}
                print(f"{lang:4} {model:13} {arm:17} {gfs:8.3f} {len(qmeans):4} "
                      f"{vs.get('GROUNDED',0):4} {vs.get('UNGROUNDED',0):4} "
                      f"{vs.get('SCALE_VIOLATION',0):4} {vs.get('UNIT_MISMATCH',0):4} {vs.get('IGNORED',0):5}")

    # ---- TR↔EN karşılaştırma (grounded kollar; birincil manzara) ----
    print("\n=== TR ↔ EN farkı (referans-GFS, grounded_noguard = ham temellendirme) ===")
    for model in [m for m in MODELS_BY_LANG.get("tr", []) if m in MODELS_BY_LANG.get("en", [])]:
        tr = summary.get((lang := "tr", model, "grounded_noguard"), {}).get("gfs")
        en = summary.get(("en", model, "grounded_noguard"), {}).get("gfs")
        if tr is not None and en is not None:
            print(f"  {model:13}: TR {tr:.3f}  vs  EN {en:.3f}   Δ(EN-TR) = {en-tr:+.3f}")

    out = RESULTS / "crosslingual_rescore.json"
    out.write_text(json.dumps({f"{l}|{m}|{a}": summary[(l, m, a)]
                               for (l, m, a) in summary}, ensure_ascii=False, indent=1), encoding="utf-8")
    # per-soru hücre-ortalamaları (eşleştirilmiş istatistik testleri için)
    cells_out = {f"{l}|{m}|{a}": {q: statistics.mean(v) for q, v in cell[(l, m, a)].items() if v}
                 for (l, m, a) in summary}
    (RESULTS / "crosslingual_cells.json").write_text(
        json.dumps(cells_out, ensure_ascii=False), encoding="utf-8")
    print(f"\n-> {out.name} + crosslingual_cells.json")


if __name__ == "__main__":
    main()
