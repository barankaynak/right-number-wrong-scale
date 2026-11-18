"""A28 — G1-MT çok turlu ek deney sürücüsü [PRE-RUN; hash'i koşu-öncesi Beyan'da].

21 eksik-girdili soru (`multiturn_turn2.json`) × 3 kol × 7 koşul (`run_g1_rerun.CONDITIONS`) × 3 tekrar.
Konuşma başına: oturum silinir → tur 1 = soru metni → tur 2 = sabit ikinci-tur mesajı (HER ZAMAN).
İki turda aynı seed (10000 + tekrar). Kol yapılandırması, referans graflar, ortam/digest
denetimi (A21-E5), ısınma (A27), MAX_ATTEMPTS ve EXCL_LIMIT G1 ile aynıdır
(`run_benchmark`, `run_g1_rerun` yardımcıları değiştirilmeden kullanılır).
Konuşma, turlarından biri fallback/error ise dışlanır (G1'deki satır kuralının konuşma karşılığı).
Kullanım (konteynerde, detached): GFP_RUN_DIR=oct_v42_mt python -m experiments.gfp_benchmark.run_multiturn
Log: results/<GFP_RUN_DIR>/mt_log.jsonl
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from experiments.gfp_benchmark.run_benchmark import (RESULTS, EnvDrift, _checked_environment,
                                                     _env_key, _load_questions, _reference_graph,
                                                     _run_environment, _stk)
from experiments.gfp_benchmark.run_g1_rerun import (ARMS, CONDITIONS, DIGESTS, EXCL_LIMIT,
                                                    MAX_ATTEMPTS, OLLAMA_VERSION, REPEATS, _warm_up)

TURN2 = json.loads((Path(__file__).resolve().parent / "multiturn_turn2.json").read_text(
    encoding="utf-8"))["questions"]


def _log(event: dict) -> None:
    event = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), **event}
    print(f"[MT] {event}", flush=True)
    with (RESULTS / "mt_log.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")


def _turn(orch, text: str, sid: str, q: dict, lang: str, ref_graphs: dict, ref_invalid: dict) -> dict:
    t0, error = time.time(), None
    try:
        out = orch.process_message(text, sid, stakeholder_type=_stk(q["stakeholder"]), lang=lang)
    except Exception as exc:                        # iz bırak, koşuyu düşürme
        out, error = {}, repr(exc)
    ref_check = None
    if q["id"] in ref_invalid:
        ref_check = {"invalid": True, "reason": ref_invalid[q["id"]]}
    elif out.get("reply"):
        try:
            rep = ref_graphs[q["id"]].check_response(out["reply"])
            ref_check = {"counts": rep.counts, "passed": rep.passed,
                         "ambiguous_matches": rep.ambiguous_matches}
        except Exception as exc:
            ref_check = {"error": repr(exc)}
    return {"user": text, "reply": out.get("reply"), "fallback": bool(out.get("fallback")),
            "provenance": out.get("provenance"), "reference_check": ref_check,
            "legacy_guard": out.get("guard"),
            "simulation_result_keys": sorted((out.get("simulation_result") or {}).keys()),
            "irradiance_source": (out.get("simulation_result") or {}).get("irradiance_source"),
            "wall_s": round(time.time() - t0, 2), "error": error}


def run_mt(model: str, lang: str, expect: tuple, qids: list[str] | None = None,
           arms: tuple = tuple(ARMS), repeats: int = REPEATS):
    """qids/arms/repeats yalnız duman testi içindir; koşu varsayılanlarla yapılır."""
    from app.core.config import settings
    from app.llm import ollama_orchestrator as oo

    RESULTS.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_env = _checked_environment(model, expect, "başlangıç")
    lang_seg = "" if lang == "tr" else f"{lang}_"
    out_path = RESULTS / f"raw_mt_{model.replace(':', '-')}_{lang_seg}{ts}.jsonl"
    questions = [q for q in _load_questions(None) if q["id"] in TURN2]
    assert len(questions) == 21
    if qids:
        questions = [q for q in questions if q["id"] in set(qids)]
    orig_tools = oo.SIMULATION_TOOLS
    ref_orch = oo.OllamaOrchestrator()
    ref_graphs, ref_invalid = {}, {}
    for q in questions:
        g, ok, reason = _reference_graph(q, ref_orch)
        if ok:
            ref_graphs[q["id"]] = g
        else:
            ref_invalid[q["id"]] = reason
    with out_path.open("w", encoding="utf-8") as fh:
        for cfg in arms:
            if cfg == "grounded_guard":
                settings.GUARD_MODE, oo.SIMULATION_TOOLS = "block", orig_tools
            elif cfg == "grounded_noguard":
                settings.GUARD_MODE, oo.SIMULATION_TOOLS = "log", orig_tools
            else:
                settings.GUARD_MODE, oo.SIMULATION_TOOLS = "log", []
            orch = oo.OllamaOrchestrator()
            orch.model = model
            for rep_i in range(repeats):
                try:
                    run_env = _checked_environment(model, expect, f"{cfg} r{rep_i}")
                except EnvDrift as exc:
                    exc.path = out_path
                    oo.SIMULATION_TOOLS = orig_tools
                    raise
                for q in questions:
                    sid = f"mt-{lang}-{cfg}-{q['id']}-r{rep_i}"
                    orch._memory.delete_session(sid)
                    orch._ollama_seed = 10_000 + rep_i
                    q_text = q["question_en"] if lang == "en" else q["question_tr"]
                    t1 = _turn(orch, q_text, sid, q, lang, ref_graphs, ref_invalid)
                    t2 = _turn(orch, TURN2[q["id"]][lang], sid, q, lang, ref_graphs, ref_invalid)
                    rec = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                           "model": orch.model, "config": cfg, "repeat": rep_i,
                           "seed": 10_000 + rep_i, "lang": lang, "question": q, "session_id": sid,
                           "turns": [t1, t2],
                           "fallback": t1["fallback"] or t2["fallback"],
                           "error": t1["error"] or t2["error"], **run_env}
                    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    fh.flush()
                    print(f"[{cfg} r{rep_i}] {q['id']}: "
                          f"{'ERR' if rec['error'] else 'FALLBACK' if rec['fallback'] else 'ok'} "
                          f"({t1['wall_s']}+{t2['wall_s']}s)", flush=True)
    oo.SIMULATION_TOOLS = orig_tools
    try:
        _checked_environment(model, expect, "bitiş")
    except EnvDrift as exc:
        exc.path = out_path
        raise
    return out_path


def _exclusion_rate(path) -> tuple[int, int, float]:
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    excl = sum(1 for r in rows if r.get("fallback") or r.get("error"))
    return len(rows), excl, (excl / len(rows) if rows else 1.0)


def _archive(path, reason: str) -> None:
    if path is not None and path.exists():
        dst = path.with_name("aborted_" + path.name)
        path.rename(dst)
        _log({"event": "archived", "file": dst.name, "reason": reason})


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    _log({"event": "start", "conditions": CONDITIONS, "repeats": REPEATS, "n_questions": len(TURN2)})
    for model, lang in CONDITIONS:
        expect = (OLLAMA_VERSION, DIGESTS[model])
        observed = _env_key(_run_environment(model))
        if observed != expect:                       # A28: yeni digest'le koşulur ve beyan edilir
            _log({"event": "digest_differs_from_G1", "model": model, "expected": expect,
                  "observed": observed})
            expect = observed
        status = "not run"
        for attempt in range(1, MAX_ATTEMPTS + 1):
            _warm_up(model, lang)
            t0 = time.time()
            _log({"event": "condition_start", "model": model, "lang": lang, "attempt": attempt})
            try:
                path = run_mt(model, lang, expect)
            except EnvDrift as exc:
                if exc.path is None:
                    _log({"event": "stop_env_mismatch_at_start", "model": model, "lang": lang,
                          "reason": str(exc)})
                    break
                _archive(exc.path, f"env drift: {exc}")
                continue
            n, excl, rate = _exclusion_rate(path)
            _log({"event": "condition_done", "model": model, "lang": lang, "file": path.name,
                  "n": n, "excluded": excl, "excl_rate": round(rate, 4),
                  "wall_h": round((time.time() - t0) / 3600, 2)})
            if rate > EXCL_LIMIT:
                _archive(path, f"exclusion rate {rate:.3f} > {EXCL_LIMIT}")
                continue
            status = "complete"
            break
        _log({"event": "condition_status", "model": model, "lang": lang, "status": status})
    _log({"event": "end"})


if __name__ == "__main__":
    main()
