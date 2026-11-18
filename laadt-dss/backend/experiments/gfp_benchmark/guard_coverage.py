"""Guard değerlendirme-kapsamı + tuzak-bayrağı ayrıştırması — A20 [EXPLORATORY, POST-OUTCOME].

Orchestrator guard'ı yalnız `pgraph.has_records` iken çalıştırır; tek-turlu G1
oturumunda araç çağrılmazsa yanıt değerlendirilmeden teslim edilir (`provenance: null`).
Bu script rapor edilen koşuları OLDUĞU GİBİ betimler (kod/LLM değişikliği yok):

    C1  grounded_guard kolunda guard-değerlendirilen yanıt payı
    C2  blok oranı: tüm yanıtlara ve değerlendirilenlere göre
    C3  değerlendirilmeyen yanıtlardan referansa karşı doğrulanamayan ≥1 sayı içerenler
    C4  değerlendirilmeyen yanıtlardan BOŞ grafa karşı ≥1 skorlanan iddia taşıyanlar
        (boş-graf politikası altında müdahaleye tabi olurdu — blok DEĞİL)
    T1  tuzak sorularında kol başına araç-çağıran yanıt payı
    T2  tuzak SCALE_VIOLATION bayraklarının mekanik ayrıştırması
  A21 ekleri (Ekim v4.2 verisi; Temmuz verisinde ilgili alanlar boş kalır):
    C2b blok oranı araçlı/araçsız kırılımı
    C5  (E2) araçsız-bloklarda yankı: UNGROUNDED iddiaların TAMAMI soru metnindeki
        sayılarla eşleşen yanıt payı (echo-only) + kısmi-yankı payı
    R   (E3) blok başına retry kırılımı: araç istedi / sayı tekrarladı / boş-hata
    D   (E4-i) guard vs noguard pre_intervention.reply özdeşliği (tam ve ≥0.95 benzerlik)

Enstrüman: guard v4.1 + kol-bağımsız referans graf (A15/A19 ile aynı).
Kullanım: python -m experiments.gfp_benchmark.guard_coverage
"""
from __future__ import annotations

import json
from collections import defaultdict
from difflib import SequenceMatcher

from experiments.gfp_benchmark.rescore_crosslingual import (
    ARMS, FILE_GLOBS, _latest, _pre_reply)
from experiments.gfp_benchmark.run_g4_final import _ref_graph_and_results
from experiments.gfp_benchmark.run_benchmark import RESULTS

SCORED = ("GROUNDED", "UNGROUNDED", "SCALE_VIOLATION", "UNIT_MISMATCH")
VIOL = ("UNGROUNDED", "SCALE_VIOLATION", "UNIT_MISMATCH")


def _t2_class(c) -> str:
    if (c.matched_key or "").startswith("input:"):
        return "a_input_echo"
    v = c.value
    if v is not None and float(v) == int(v) and 0 <= v <= 100:
        return "b_small_integer"
    return "c_other"


def _question_values(text: str) -> list[float]:
    """Soru metnindeki tüm sayı adayları (guard'ın kendi ayrıştırıcısıyla)."""
    from app.llm.provenance_guard import _NUM_RE, _candidate_values
    vals: list[float] = []
    for m in _NUM_RE.finditer(text or ""):
        c = _candidate_values(m.group("num"), m.group("mag"))
        if m.group("pct") or m.group("pct2"):
            c = c + [x / 100.0 for x in c]
        vals.extend(c)
    return vals


def main() -> None:
    from app.llm import ollama_orchestrator as oo
    from app.llm.provenance_guard import ProvenanceGraph, _matches
    orch = oo.OllamaOrchestrator()
    # check_response boş grafta erken döner (iddia skorlamaz) → C4 için hiçbir sayıyla
    # eşleşemeyecek TEK nöbetçi kayıt: her iddia ya IGNORED ya UNGROUNDED olur.
    empty = ProvenanceGraph()
    empty.load_records([{"key": "__sentinel__", "value": 1e18, "scale": "building"}])
    # v4.2: gerçek boş graf da skorlar (A21) — C5 bunu kullanır (canlı guard'la aynı yol)
    empty_noref = ProvenanceGraph()

    ref_cache: dict = {}

    def ref_graph(q):
        if q["id"] not in ref_cache:
            ref_cache[q["id"]] = _ref_graph_and_results(q, orch)[0]
        return ref_cache[q["id"]]

    cov = defaultdict(lambda: defaultdict(int))     # (lang, model) -> C1–C4 sayaçları
    t1 = defaultdict(lambda: defaultdict(int))      # (lang, model, arm) -> n / tool
    t2 = defaultdict(lambda: defaultdict(int))      # arm -> sınıf -> sayı
    t2_other = []
    a21 = defaultdict(lambda: defaultdict(int))     # (lang, model) -> A21 sayaçları
    pre_by = defaultdict(dict)                      # (lang, model) -> (qid, rep, arm) -> pre

    for (lang, model), pattern in FILE_GLOBS.items():
        f = _latest(pattern)
        if not f:
            continue
        rows = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
        for rec in rows:
            arm = rec.get("config")
            if arm not in ARMS or rec.get("fallback") or rec.get("error"):
                continue
            q = rec["question"]
            prov = rec.get("provenance")
            pre = _pre_reply(rec) or rec.get("reply") or ""
            is_trap = q.get("scale_focus") == "cross"

            if arm in ("grounded_guard", "grounded_noguard") and prov is not None:
                pre_by[(lang, model)][(q["id"], rec.get("repeat"), arm)] = pre
            if arm == "grounded_guard" and prov is not None:
                k = a21[(lang, model)]
                toolless = prov.get("n_records") == 0
                k["evaluated"] += 1
                k["toolless"] += int(toolless)
                if prov.get("blocked"):
                    k["blocked_toolless" if toolless else "blocked_tool"] += 1
                    if prov.get("retry_tool_calls_requested"):
                        k["block_retry_requested_tool"] += 1
                    elif prov.get("retry_error") or prov.get("retry_content_empty"):
                        k["block_retry_empty_or_error"] += 1
                    else:
                        k["block_retry_restated_numbers"] += 1
                    if toolless and pre:
                        qtext = q.get("question_en") if lang == "en" else q.get("question_tr")
                        qvals = _question_values(qtext)
                        ung = [cl for cl in empty_noref.check_response(pre).claims
                               if cl.verdict == "UNGROUNDED"]
                        echo = [any(_matches(cl.value, qv) or _matches(cl.value / 100.0, qv)
                                    for qv in qvals) for cl in ung]
                        if ung and all(echo):
                            k["blocked_toolless_echo_only"] += 1
                        elif any(echo):
                            k["blocked_toolless_partial_echo"] += 1
            if arm == "grounded_guard":
                c = cov[(lang, model)]
                c["n"] += 1
                if prov is not None:
                    c["evaluated"] += 1
                    c["blocked"] += int(bool(prov.get("blocked")))
                    c["retried"] += int(bool(prov.get("retried")))
                else:
                    c["not_evaluated"] += 1
                    g = ref_graph(q)
                    if g is not None and pre:
                        rc = g.check_response(pre).counts
                        c["not_eval_ref_scored"] += int(sum(rc.get(k, 0) for k in SCORED) > 0)
                        c["not_eval_ref_unverifiable"] += int(sum(rc.get(k, 0) for k in VIOL) > 0)
                    if pre:
                        ec = empty.check_response(pre).counts
                        c["not_eval_empty_graph_scored"] += int(sum(ec.get(k, 0) for k in SCORED) > 0)

            if is_trap:
                k1 = t1[(lang, model, arm)]
                k1["n"] += 1
                k1["called_tool"] += int(prov is not None and bool(prov.get("tools_used")))
                g = ref_graph(q)
                if g is not None and pre:
                    for cl in g.check_response(pre).claims:
                        if cl.verdict != "SCALE_VIOLATION":
                            continue
                        cls = _t2_class(cl)
                        t2[arm][cls] += 1
                        t2["all"][cls] += 1
                        if cls == "c_other":
                            t2_other.append({"lang": lang, "model": model, "arm": arm,
                                             "qid": q["id"], "claim": cl.text,
                                             "value": cl.value, "matched_key": cl.matched_key,
                                             "record_scale": cl.record_scale,
                                             "claimed_scales": cl.claimed_scales,
                                             "sentence": cl.sentence})

    out = {"coverage_grounded_guard": {}, "trap_tool_use": {}, "trap_sv_decomposition": {},
           "trap_sv_other": t2_other, "a21_guard_arm": {}, "a21_pre_identity": {}}
    for (lang, model), k in a21.items():
        row = dict(k)
        bt = k["blocked_toolless"]
        row["echo_only_share_of_toolless_blocks"] = (
            round(k["blocked_toolless_echo_only"] / bt, 4) if bt else None)
        row["partial_echo_share_of_toolless_blocks"] = (
            round(k["blocked_toolless_partial_echo"] / bt, 4) if bt else None)
        out["a21_guard_arm"][f"{lang}|{model}"] = row
    for (lang, model), d in pre_by.items():
        keys = {(qid, rep) for (qid, rep, arm) in d}
        pairs = [(d.get((qid, rep, "grounded_guard")), d.get((qid, rep, "grounded_noguard")))
                 for (qid, rep) in keys]
        pairs = [(x, y) for x, y in pairs if x is not None and y is not None]
        if pairs:
            out["a21_pre_identity"][f"{lang}|{model}"] = {
                "n_pairs": len(pairs),
                "identical": round(sum(x == y for x, y in pairs) / len(pairs), 4),
                "similar_ge_0_95": round(sum(SequenceMatcher(None, x, y).ratio() >= 0.95
                                             for x, y in pairs) / len(pairs), 4)}
    print("=== C1–C4: grounded_guard kolu, guard değerlendirme-kapsamı ===")
    for (lang, model), c in cov.items():
        n, ev = c["n"], c["evaluated"]
        row = dict(c)
        row.update({"evaluated_share": ev / n if n else None,
                    "blocked_share_all": c["blocked"] / n if n else None,
                    "blocked_share_evaluated": c["blocked"] / ev if ev else None})
        out["coverage_grounded_guard"][f"{lang}|{model}"] = row
        print(f"{lang:3} {model:21} n={n:3} evaluated={ev:3} ({ev/n:5.1%}) "
              f"blocked={c['blocked']:3} ({c['blocked']/n:5.1%} all, "
              f"{(c['blocked']/ev if ev else 0):5.1%} eval) | not-eval={c['not_evaluated']:3}: "
              f"ref-unverifiable={c['not_eval_ref_unverifiable']:3} "
              f"empty-graph-scored={c['not_eval_empty_graph_scored']:3}")

    print("\n=== T1: tuzak soruları, araç-çağıran yanıt payı ===")
    for (lang, model, arm), k in t1.items():
        out["trap_tool_use"][f"{lang}|{model}|{arm}"] = dict(k)
        print(f"{lang:3} {model:21} {arm:17} {k['called_tool']:2}/{k['n']:2}")

    print("\n=== T2: tuzak SCALE_VIOLATION bayrakları, mekanik ayrıştırma ===")
    for arm, d in t2.items():
        out["trap_sv_decomposition"][arm] = dict(d)
        tot = sum(d.values())
        print(f"{arm:17} toplam={tot:3} " + " ".join(f"{k}={v}" for k, v in sorted(d.items())))

    (RESULTS / "guard_coverage.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n-> guard_coverage.json (c_other={len(t2_other)})")


if __name__ == "__main__":
    main()
