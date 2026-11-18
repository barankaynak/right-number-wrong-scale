"""G4 NİHAİ — hata-enjeksiyonu recall: GFP-provenance vs legacy-regex.

Danışman v2.10 tasarım-onayı (SCIENTIFIC_REVIEW §8). Ön-kayıt PREREGISTRATION §9
amendment A9 [PRE-OUTCOME]. Bu, guard etiketlerine BAĞIMSIZ geçerlilik veren
kilit-taşı deney: G1 grounded-TEMİZ yanıtlarına kontrollü hata enjekte edip iki
guard'ın yakalama oranını (recall) eşleştirilmiş karşılaştırır.

Tasarım (donmuş kararlar):
- Analiz-birimi = qid; her (qid, kategori) için İLK-UYGULANABİLİR temsilci
  (determinist sıra: model[gemma<qwen] → config[noguard<guard-müdahalesiz] → repeat;
  uygulanabilirlik = enjeksiyon non-None + atıf-garantisi; SONUÇ-KÖR seçim).
- Atıf-garantisi: kaynak (orijinal) metin referans-grafta 0 ihlal + GROUNDED≥1.
- Enjeksiyon: value_fab GROUNDED-hedefli (×U[1.5,3.0], çarpan kayıtlı, IGNORED-hedef
  kontaminasyonu engellenir); unit_swap/scale_swap/small_int → inject_errors.inject()
  (bayt-aynı, frozen). scale_swap'ın enjekte ettiği sayma-sayısı IGNORED (blocker#3 test-kilitli).
- Notlama: GFP birincil = referans-graf (çakışma-MUHAFAZAKÂR); GFP ikincil = in-run
  graf (tool_trace'ten determinist yeniden-koşu). Legacy 3-okuma: birincil =
  validate_response(mutated, last_result)/violations (deploy-sadık); S1 = +warnings
  (frozen davranış); S2 = cömertlik-tavanı (her araç-sonucuna ayrı, any-detect).
- Kontroller: bozulmamış kaynak → FP (her okumada simetrik).
- Güç-katmanı: Tier-1 = scale_swap+unit_swap (manşet, n≥30); Tier-2 = value_fab+small_int
  (exact test, dürüst-n). value_fab çarpan-katmanı (<2× / ≥2×) ayrı raporlanır.

Kullanım: python -m experiments.gfp_benchmark.run_g4_final [--seed 42] [--limit N]
"""
from __future__ import annotations
import argparse
import json
import random
from datetime import datetime, timezone
from pathlib import Path

from experiments.gfp_benchmark.inject_errors import inject, _fmt, CATEGORIES
from experiments.gfp_benchmark.run_benchmark import _stk, _resolve_prev_refs, RESULTS

HERE = Path(__file__).resolve().parent

TIER1 = ("scale_swap", "unit_swap")          # manşet: legacy yapısal-kör
TIER2 = ("value_fabrication", "small_int_fabrication")
MODEL_RANK = {"gemma4:e4b": 0, "qwen3.5:27b": 1}
CONFIG_RANK = {"grounded_noguard": 0, "grounded_guard": 1}


def _ref_graph_and_results(q, orch):
    """Kol-bağımsız tam-zincir referans grafı + araç-sonucu dict listesi."""
    from app.llm.provenance_guard import ProvenanceGraph
    g = ProvenanceGraph()
    stakeholder = _stk(q["stakeholder"])
    per_step = q.get("suggested_args_per_step")
    prior, results = [], []
    for i, tool in enumerate(q.get("expected_tools", [])):
        if per_step and i < len(per_step):
            raw = dict(per_step[i] or {})
        elif i == 0:
            raw = dict(q.get("suggested_args") or {})
        else:
            return None, None
        raw.pop("stakeholder_type", None)
        try:
            args = _resolve_prev_refs(raw, prior)
            result = orch._execute_tool(tool, args, stakeholder)
        except Exception:
            return None, None
        if not isinstance(result, dict) or result.get("status") == "simulation_failed":
            return None, None
        g.add_tool_result(tool, args, stakeholder, result)
        prior.append(result)
        results.append(result)
    return (g, results) if g.has_records else (None, None)


def _inrun_graph(rec, orch):
    """tool_trace'ten determinist yeniden-koşu ile in-run graf (GFP ikincil)."""
    from app.llm.provenance_guard import ProvenanceGraph
    g = ProvenanceGraph()
    stakeholder = _stk(rec["question"]["stakeholder"])
    for step in ((rec.get("provenance") or {}).get("tool_trace") or []):
        tool, args = step.get("tool"), dict(step.get("args") or {})
        try:
            result = orch._execute_tool(tool, args, stakeholder)
            if isinstance(result, dict) and result.get("status") != "simulation_failed":
                g.add_tool_result(tool, args, stakeholder, result)
        except Exception:
            pass
    return g if g.has_records else None


def _inject_value_fab_grounded(text, ref_graph, rng, lang="tr"):
    """value_fab: YALNIZ referans-grafta GROUNDED eşleşen bir sayıyı, KENDİ CÜMLESİ
    içinde boz (IGNORED-hedef + liste-madde-numarası kontaminasyonu yok — global
    text.replace liste-işaretini bozuyordu, cümle-yerel düzeltme). Döner:
    (mutated, mult, orig_val) | None."""
    rep = ref_graph.check_response(text)
    grounded = [c for c in rep.claims
                if c.verdict == "GROUNDED" and c.sentence and c.text in c.sentence
                and c.sentence in text]
    if not grounded:
        return None
    c = rng.choice(grounded)
    mult = rng.uniform(1.5, 3.0)
    new_sentence = c.sentence.replace(c.text, _fmt(c.value * mult, lang), 1)
    if new_sentence == c.sentence:
        return None
    mutated = text.replace(c.sentence, new_sentence, 1)
    if mutated == text:
        return None
    return mutated, round(mult, 3), c.value


def _source_text(rec):
    """Modelin grounded-temiz DOĞAL çıktısı (guard müdahalesi SONRASI safe_summary DEĞİL)."""
    return rec.get("reply") or ""


def _clean_source(rec):
    """Kaynak grounded-temiz mi? guard-kolunda BLOKLANMAMIŞ olmalı (final=model çıktısı)."""
    if rec.get("fallback") or rec.get("error"):
        return False
    if rec["config"] not in CONFIG_RANK:
        return False
    if rec["config"] == "grounded_guard" and (rec.get("provenance") or {}).get("blocked"):
        return False
    rc = rec.get("reference_check") or {}
    c = rc.get("counts") or {}
    if not rc.get("passed") or c.get("GROUNDED", 0) <= 0:
        return False
    return not any(c.get(k, 0) for k in ("UNGROUNDED", "SCALE_VIOLATION", "UNIT_MISMATCH"))


def _legacy_readings(mutated, results):
    """(primary, s1_warnings, s2_ceiling) tespit bayrakları."""
    from app.llm.hallucination_guard import validate_response
    last = results[-1] if results else None
    vr = validate_response(mutated, last)
    primary = not vr.passed
    s1 = primary or bool(vr.warnings)
    s2 = any((not (r2 := validate_response(mutated, res)).passed) or bool(r2.warnings)
             for res in results)
    return primary, s1, s2


def run(seed: int, limit: int | None, lang: str = "tr", source_model: str | None = None) -> Path:
    from app.llm import ollama_orchestrator as oo
    orch = oo.OllamaOrchestrator()
    rng = random.Random(seed)

    # CROSS-LINGUAL: dile göre G1 kaynak dosyaları (EN = _en_ dosyaları)
    # source_model: yalnız o modelin yanıtlarından enjekte (A16 3. model Mistral-only G4;
    # frozen gemma+qwen G4 setine DOKUNMAZ). None → varsayılan gemma+qwen havuzu.
    seg = "" if lang == "tr" else f"{lang}_"
    import glob
    files = []
    model_tag = ""
    if source_model:
        slug = source_model.replace(":", "-")
        model_tag = slug + "_"
        pat = f"raw_g1_{slug}_{seg}2026*.jsonl" if lang == "tr" else f"raw_g1_{slug}_{seg}*.jsonl"
        hits = sorted(glob.glob(str(RESULTS / pat)))
        if hits:
            files.append(Path(hits[-1]))
    else:
        for m in ("gemma4-e4b", "qwen3.5-27b"):
            pat = f"raw_g1_{m}_{seg}2026070*.jsonl" if lang == "tr" else f"raw_g1_{m}_{seg}*.jsonl"
            hits = sorted(glob.glob(str(RESULTS / pat)))
            if hits:
                files.append(Path(hits[-1]))

    # kaynak havuz: grounded-temiz, determinist sırada
    pool = []
    for f in files:
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                if _clean_source(r):
                    pool.append(r)
    pool.sort(key=lambda r: (MODEL_RANK.get(r["model"], 9),
                             CONFIG_RANK.get(r["config"], 9), r.get("repeat", 0)))

    by_qid = {}
    for r in pool:
        by_qid.setdefault(r["question"]["id"], []).append(r)
    qids = sorted(by_qid)
    if limit:
        qids = qids[:limit]

    ref_cache = {}          # qid -> (graph, results)

    def _ref(qid):
        if qid not in ref_cache:
            ref_cache[qid] = _ref_graph_and_results(by_qid[qid][0]["question"], orch)
        return ref_cache[qid]

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = RESULTS / f"raw_g4_final_{model_tag}{seg}seed{seed}_{ts}.jsonl"
    n_inj = 0
    controls_done = set()
    with out_path.open("w", encoding="utf-8") as fh:
        for qid in qids:
            g, results = _ref(qid)
            if g is None:
                continue
            for cat in CATEGORIES:
                chosen = None
                for rec in by_qid[qid]:
                    src = _source_text(rec)
                    if not src:
                        continue
                    # atıf-garantisi: kaynak referans-grafta temiz + GROUNDED≥1
                    sc = g.check_response(src)
                    if not sc.passed or sc.counts.get("GROUNDED", 0) <= 0:
                        continue
                    # enjeksiyon
                    mult = orig_val = None
                    if cat == "value_fabrication":
                        got = _inject_value_fab_grounded(src, g, rng, lang)
                        if got is None:
                            continue
                        mutated, mult, orig_val = got
                    else:
                        mutated = inject(src, cat, rng, lang)
                        if mutated is None or mutated == src:
                            continue
                    chosen = (rec, src, mutated, mult, orig_val)
                    break
                if chosen is None:
                    continue
                rec, src, mutated, mult, orig_val = chosen
                n_inj += 1

                gfp_ref = g.check_response(mutated)
                inrun = _inrun_graph(rec, orch)
                gfp_inrun = inrun.check_response(mutated) if inrun else None
                leg_p, leg_s1, leg_s2 = _legacy_readings(mutated, results)

                fh.write(json.dumps({
                    "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "kind": "injected", "category": cat, "qid": qid,
                    "model": rec["model"], "config": rec["config"], "repeat": rec.get("repeat"),
                    "scale_focus": rec["question"].get("scale_focus"),
                    "chain_length": rec["question"].get("chain_length"),
                    "value_fab_multiplier": mult, "value_fab_orig": orig_val,
                    # B4 mutasyon-kalitesi insan-kodlaması için metinler (ek; tespit
                    # mantığını ETKİLEMEZ — determinist seed=42 aynı 109 enjeksiyonu üretir)
                    "source": src, "mutated": mutated,
                    "gfp_ref_detected": not gfp_ref.passed,
                    "gfp_ref_counts": gfp_ref.counts,
                    "gfp_inrun_detected": (None if gfp_inrun is None else not gfp_inrun.passed),
                    "legacy_primary_detected": leg_p,
                    "legacy_s1_warn_detected": leg_s1,
                    "legacy_s2_ceiling_detected": leg_s2,
                }, ensure_ascii=False) + "\n")

                # kontrol (qid başına bir kez, bozulmamış kaynak → FP)
                if qid not in controls_done:
                    controls_done.add(qid)
                    cref = g.check_response(src)
                    cinrun = inrun.check_response(src) if inrun else None
                    cl_p, cl_s1, cl_s2 = _legacy_readings(src, results)
                    fh.write(json.dumps({
                        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        "kind": "control", "category": None, "qid": qid,
                        "model": rec["model"], "config": rec["config"],
                        "source": src, "mutated": src,
                        "gfp_ref_detected": not cref.passed,
                        "gfp_inrun_detected": (None if cinrun is None else not cinrun.passed),
                        "legacy_primary_detected": cl_p,
                        "legacy_s1_warn_detected": cl_s1,
                        "legacy_s2_ceiling_detected": cl_s2,
                    }, ensure_ascii=False) + "\n")

    print(f"{n_inj} enjeksiyon + {len(controls_done)} kontrol → {out_path.name}")
    return out_path


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--lang", default="tr", choices=["tr", "en"])
    ap.add_argument("--source-model", default=None,
                    help="yalnız bu modelin yanıtlarından enjekte (ör. mistral-small3.2:24b)")
    a = ap.parse_args()
    run(a.seed, a.limit, lang=a.lang, source_model=a.source_model)
