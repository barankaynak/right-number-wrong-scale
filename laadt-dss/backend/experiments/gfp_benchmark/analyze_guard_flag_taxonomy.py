"""Guard canlı-flag taksonomisi (v2.12 bulgusu, A11 amendment).

BULGU: Guard'ın canlı bloklu yanıtlarda işaretlediği sayılar, DEĞER-EŞLEŞTİRME
kanalının iki-yönlü doygunluğunu gösterir — çoğu flag GERÇEK uydurma DEĞİL:
format/persentil/yuvarlama artefaktı ya da değer-eşleştiricinin (guard'ın ve bu
script'in AYNI zaafı) çözemediği meşru sayılar (ör. 1.1024 pu ↔ referans 1,102).

Bu, "guard N canlı uydurma yakaladı" iddiasının değer-eşleştirmeyle KURULAMAZ
olduğunu kanıtlar → guard "hata-dedektörü" değil "fail-closed doğrulanabilirlik-
filtresi"; ve provenance'ın DEĞER-ÖTESİ alanları (fonksiyon/ölçek/birim/bağlam)
tam bu yüzden gerekli (GFP varlık-gerekçesi). Guard'ın kendi UNGROUNDED kanalı da
bu sınırı miras alır (dürüstçe teslim edilir).

DİKKAT: 'unresolved_by_value_matching' kategorisi DOĞRULANMIŞ UYDURMA DEĞİLDİR —
değer-eşleştirmenin ayıramadığı (format-varyansı dahil) artıktır. Bu belirsizlik
bulgunun kendisidir. Hiçbir canlı-sayım (UNGROUNDED/SCALE/UNIT) iddialaşmaz.

Kullanım: python -m experiments.gfp_benchmark.analyze_guard_flag_taxonomy
"""
from __future__ import annotations
import glob
import json
import os
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
# A21: yeniden-koşu alt-dizini (GFP_RUN_DIR); boşsa Temmuz düzeni
RESULTS = HERE / "results" / os.environ.get("GFP_RUN_DIR", "")
_VIOL = ("UNGROUNDED", "SCALE_VIOLATION", "UNIT_MISMATCH")
_TOL = 0.02


def _ref_values(question, orch) -> list[float]:
    from experiments.gfp_benchmark.run_g4_final import _ref_graph_and_results
    g, _ = _ref_graph_and_results(question, orch)
    if g is None:
        return []
    return [abs(d["value"]) for d in g.records_as_dicts()
            if isinstance(d.get("value"), (int, float))]


def _latest_per_model() -> list[Path]:
    out = []
    # A21: tarih-bağımsız; Temmuz dizininde sorted()[-1] aynı dosyayı seçer
    # Beyan 2026-11-05: A24'ün Model B'si qwen3.8 bu glob'a eklenmemişti (Ekim'de yalnız A-TR
    # okunuyordu); Temmuz dizininde qwen3.8, Ekim dizininde qwen3.5 hiçbir şeyle eşleşmez.
    for pat in ("raw_g1_gemma4-e4b_2026*T*.jsonl", "raw_g1_qwen3.5-27b_2026*T*.jsonl",
                "raw_g1_qwen3.8-27b_2026*T*.jsonl"):
        hits = sorted(glob.glob(str(RESULTS / pat)))
        if hits:
            out.append(Path(hits[-1]))
    return out


def run() -> dict:
    from app.llm import ollama_orchestrator as oo
    from experiments.gfp_benchmark.run_g4_final import _inrun_graph
    orch = oo.OllamaOrchestrator()

    blocked = []
    for f in _latest_per_model():
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                if (r.get("provenance") or {}).get("blocked"):
                    blocked.append(r)

    ref_cache: dict = {}
    cat = {"value_matches_reference_FP": 0, "percentile_or_pct_label": 0,
           "small_int_context": 0, "unresolved_by_value_matching": 0}
    total = 0
    n_analysed = 0      # A21: in-run grafı olan (araç çağıran) bloklar; boş-graf blokları
    examples = []       # _inrun_graph=None ile dışarıda kalır (taksonomi = GFP in-run bayrakları)
    for r in blocked:
        qid = r["question"]["id"]
        if qid not in ref_cache:
            ref_cache[qid] = _ref_values(r["question"], orch)
        refs = ref_cache[qid]
        g = _inrun_graph(r, orch)
        pre = ((r.get("provenance") or {}).get("pre_intervention") or {}).get("reply") or ""
        if g is None or not pre:
            continue
        n_analysed += 1
        for c in g.check_response(pre).claims:
            if c.verdict not in _VIOL:
                continue
            total += 1
            v = abs(c.value)
            sent = c.sentence or ""
            matched = any(rv > 0 and abs(v - rv) / rv <= _TOL for rv in refs)
            is_int = (v == int(v))
            perc = (bool(re.search(r"P\d+", sent)) or ("%" + c.text) in sent
                    or bool(re.search(r"P\d+/P\d+", sent)))
            if matched:
                cat["value_matches_reference_FP"] += 1
            elif perc:
                cat["percentile_or_pct_label"] += 1
            elif is_int and v <= 30:
                cat["small_int_context"] += 1
            else:
                cat["unresolved_by_value_matching"] += 1
                if len(examples) < 12:
                    examples.append({"qid": qid, "text": c.text, "verdict": c.verdict,
                                     "sentence": sent[:90]})
    return {"n_blocked_responses": len(blocked),
            "n_blocked_analysed_with_inrun_graph": n_analysed,
            "n_flags": total,
            "categories": cat,
            "category_pct": {k: (round(100 * v / total, 1) if total else 0)
                             for k, v in cat.items()},
            "note": ("'unresolved_by_value_matching' DOĞRULANMIŞ UYDURMA DEĞİL — "
                     "değer-eşleştiricinin (guard ve bu script AYNI zaaf) çözemediği "
                     "artık; örnekleri sık sık meşru sayılardır (gerilim 1.1024↔1,102). "
                     "Hiçbir canlı-sayım iddialaşmaz."),
            "examples_unresolved": examples}


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
