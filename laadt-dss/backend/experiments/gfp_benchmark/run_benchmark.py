"""
G1 benchmark koşucusu — grounded/ungrounded/guard-ablasyon kolları.

Kullanım (container içinde):
    python -m experiments.gfp_benchmark.run_benchmark --limit 3 --configs grounded_guard
    python -m experiments.gfp_benchmark.run_benchmark --model gemma4:e4b

Kollar (G1):
    grounded_guard   : araçlar AÇIK + GUARD_MODE=block   (tam GFP)
    grounded_noguard : araçlar AÇIK + GUARD_MODE=log     (guard marjinal-katkı ablasyonu)
    ungrounded       : araçlar KAPALI (çıplak LLM)        (temellendirme ablasyonu)

Çıktı: results/raw_g1_<model>_<ts>.jsonl — HAM izler (soru, kol, yanıt,
provenance raporu, legacy guard, süre). GFS BURADA HESAPLANMAZ — metrik
formülü ve ağırlıklar PREREGISTRATION.md'de dondurulur (A2), analiz ayrı
script'te yapılır. Ham izler saklanır (tekrarlanabilirlik).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
# A21: yeniden-koşu izleri ayrı alt-dizine (ör. GFP_RUN_DIR=oct_v42); boşsa Temmuz düzeni
RESULTS = HERE / "results" / os.environ.get("GFP_RUN_DIR", "")


def _run_environment(model_name: str) -> dict:
    """A21: iz-başına sunucu/model/guard kimliği. Temmuz koşularında kaydedilmediği için
    aynı seed'le çıktılar sürüm-ötesi yeniden üretilemedi (A21 gerekçesi)."""
    import httpx
    from app.core.config import settings
    env = {"ollama_version": None, "model_digest": None,
           "guard_sha256": hashlib.sha256(
               (HERE.parent.parent / "app" / "llm" / "provenance_guard.py").read_bytes()
           ).hexdigest(),
           # A23: ışınım önbelleğinin kimliği (koşu boyunca sabit olmalı)
           "tmy_manifest_sha256": hashlib.sha256(
               (HERE.parent.parent / "app" / "simulation" / "pv" / "tmy_cache"
                / "MANIFEST.json").read_bytes()
           ).hexdigest()}
    try:
        host = settings.OLLAMA_HOST.rstrip("/")
        env["ollama_version"] = httpx.get(f"{host}/api/version", timeout=10).json().get("version")
        for m in httpx.get(f"{host}/api/tags", timeout=10).json().get("models", []):
            if m.get("name") == model_name:
                env["model_digest"] = m.get("digest")
    except Exception as exc:                      # kimlik alınamazsa koşu durmaz, iz bırakır
        env["env_error"] = repr(exc)
    return env


class EnvDrift(RuntimeError):
    """A21-E5: sunucu/model kimliği koşu içinde ya da A21 tablosundan saptı."""
    path: "Path | None" = None


def _env_key(env: dict) -> tuple:
    return (env.get("ollama_version"), env.get("model_digest"))


def _checked_environment(model_name: str, reference: tuple, where: str) -> dict:
    """Kimliği (geçici ağ hatasına karşı 3 deneme) sorgula; referanstan sapıyorsa EnvDrift."""
    env = _run_environment(model_name)
    for _ in range(2):
        if _env_key(env) == reference:
            break
        time.sleep(15)
        env = _run_environment(model_name)
    if _env_key(env) != reference:
        raise EnvDrift(f"{where}: kimlik {_env_key(env)} != beklenen {reference}")
    return env


def _load_questions(limit: int | None):
    qs = json.loads((HERE / "questions.json").read_text(encoding="utf-8"))["questions"]
    return qs[:limit] if limit else qs


def _resolve_prev_refs(args: dict, prior_results: list[dict]) -> dict:
    """"$prev.<key>" işaretçilerini ÖNCEKİ adım sonuçlarından çözer — geriye
    doğru arar (en yakın önce): sta-10 gibi zincirlerde policy'nin
    system_cost_tl'si bir-önceki grid adımında değil, 2 adım gerideki
    fizibilite adımındadır."""
    out = {}
    for k, v in (args or {}).items():
        if isinstance(v, str) and v.startswith("$prev."):
            key = v[len("$prev."):]
            for res in reversed(prior_results):
                if isinstance(res, dict) and res.get(key) is not None:
                    out[k] = res[key]
                    break
            else:
                raise ValueError(f"$prev.{key} çözülemedi (önceki adımların hiçbirinde yok)")
        else:
            out[k] = v
    return out


def _reference_graph(question: dict, orch):
    """KRİTİK-7/F1: soru başına KOL-BAĞIMSIZ, TAM-ZİNCİR referans grafı —
    expected_tools'un TÜM adımları, adım-başına argümanlarla
    (suggested_args_per_step; yoksa suggested_args) LLM'siz doğrudan çalıştırılır.
    Tek-adım referans, chain-2/3 sorularda grounded yanıtı sahte-UNGROUNDED
    yapıp H_G2'yi inşa-gereği doğrulardı (ölçüm artefaktı).

    Dönen: (graf, valid: bool, invalid_reason) — boş/başarısız referans FAIL-FAST
    (soru analizden kayıtlı-dışlanır; sessizce devam edilmez)."""
    from app.llm.provenance_guard import ProvenanceGraph
    g = ProvenanceGraph()
    stakeholder = _stk(question["stakeholder"])
    tools = question.get("expected_tools", [])
    per_step = question.get("suggested_args_per_step")
    prior_results: list[dict] = []

    for i, tool in enumerate(tools):
        if per_step and i < len(per_step):
            raw = dict(per_step[i] or {})
        elif i == 0:
            raw = dict(question.get("suggested_args") or {})
        else:
            return g, False, f"adım-{i} için suggested_args_per_step yok (chain sorusu)"
        raw.pop("stakeholder_type", None)
        try:
            args = _resolve_prev_refs(raw, prior_results)
            result = orch._execute_tool(tool, args, stakeholder)
        except Exception as exc:
            return g, False, f"adım-{i} ({tool}) çalıştırılamadı: {exc!r}"
        if not isinstance(result, dict) or result.get("status") == "simulation_failed":
            return g, False, f"adım-{i} ({tool}) simulation_failed: {str(result)[:120]}"
        n_before = len(g.records)
        g.add_tool_result(tool, args, stakeholder, result)
        if len(g.records) == n_before:
            return g, False, f"adım-{i} ({tool}) grafa kayıt eklemedi"
        prior_results.append(result)

    if not g.has_records:
        return g, False, "referans grafı boş"
    return g, True, None


def run(model: str | None, configs: list[str], limit: int | None,
        session_prefix: str = "g1", repeats: int = 1, lang: str = "tr",
        qids: list[str] | None = None, file_prefix: str = "raw_g1",
        expect_env: tuple | None = None) -> Path:
    """expect_env: A21 tablosundaki (ollama_version, model_digest); verilirse başlangıçta,
    her (kol, tekrar) başında ve sonda doğrulanır — sapma EnvDrift (A21-E5)."""
    from app.core.config import settings
    from app.llm import ollama_orchestrator as oo

    RESULTS.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    model_name = model or settings.OLLAMA_MODEL
    run_env = _run_environment(model_name)
    print(f"[ENV] {run_env}")
    reference = _env_key(run_env)
    if expect_env is not None:
        run_env = _checked_environment(model_name, tuple(expect_env), "başlangıç")
        reference = tuple(expect_env)
    # CROSS-LINGUAL: EN koşusu ayrı-adlı dosyaya yazar (_en_); TR geriye-uyumlu (segment yok)
    lang_seg = "" if lang == "tr" else f"{lang}_"
    out_path = RESULTS / f"{file_prefix}_{model_name.replace(':', '-')}_{lang_seg}{ts}.jsonl"

    questions = _load_questions(limit)
    if qids:
        questions = [q for q in questions if q["id"] in set(qids)]
    orig_tools = oo.SIMULATION_TOOLS

    # Referans graflar bir kez (araçlar deterministik; PVGIS cache'li).
    # FAIL-FAST: referansı kurulamayan soru kayıtlı-dışlanır (sessiz devam YOK).
    ref_orch = oo.OllamaOrchestrator()
    ref_graphs: dict = {}
    ref_invalid: dict = {}
    for q in questions:
        g, ok, reason = _reference_graph(q, ref_orch)
        if ok:
            ref_graphs[q["id"]] = g
        else:
            ref_invalid[q["id"]] = reason
            print(f"[REF-INVALID] {q['id']}: {reason}")
    if ref_invalid:
        print(f"UYARI: {len(ref_invalid)} sorunun referansı kurulamadı — "
              f"bu sorular koşulur ama reference_check=invalid işaretlenir.")

    with out_path.open("w", encoding="utf-8") as fh:
        for cfg in configs:
            # Kol yapılandırması
            if cfg == "grounded_guard":
                settings.GUARD_MODE = "block"
                oo.SIMULATION_TOOLS = orig_tools
            elif cfg == "grounded_noguard":
                settings.GUARD_MODE = "log"
                oo.SIMULATION_TOOLS = orig_tools
            elif cfg == "ungrounded":
                settings.GUARD_MODE = "log"     # denetim raporu yine toplanır (ölçüm)
                oo.SIMULATION_TOOLS = []        # çıplak LLM — araç yok
            else:
                raise ValueError(f"bilinmeyen kol: {cfg}")

            orch = oo.OllamaOrchestrator()
            if model:
                orch.model = model

            for rep_i in range(repeats):
                if expect_env is not None:          # A21-E5: tekrar başı drift denetimi
                    try:
                        run_env = _checked_environment(model_name, reference,
                                                       f"{cfg} r{rep_i}")
                    except EnvDrift as exc:
                        exc.path = out_path
                        raise
                for q in questions:
                    sid = f"{session_prefix}-{lang}-{cfg}-{q['id']}-r{rep_i}"
                    orch._memory.delete_session(sid)
                    # Tekrarlanabilirlik: hücre-başına deterministik seed (A2)
                    orch._ollama_seed = 10_000 + rep_i
                    t0 = time.time()
                    error = None
                    q_text = q["question_en"] if lang == "en" else q["question_tr"]
                    try:
                        out = orch.process_message(q_text, sid,
                                                   stakeholder_type=_stk(q["stakeholder"]),
                                                   lang=lang)
                    except Exception as exc:        # iz bırak, koşuyu düşürme
                        out, error = {}, repr(exc)
                    # ORTA-9a/KRİTİK-7: kol-bağımsız TAM-ZİNCİR referans notlaması
                    ref_check = None
                    if q["id"] in ref_invalid:
                        ref_check = {"invalid": True, "reason": ref_invalid[q["id"]]}
                    elif out.get("reply"):
                        try:
                            ref_rep = ref_graphs[q["id"]].check_response(out["reply"])
                            ref_check = {"counts": ref_rep.counts,
                                         "passed": ref_rep.passed,
                                         "ambiguous_matches": ref_rep.ambiguous_matches}
                        except Exception as exc:
                            ref_check = {"error": repr(exc)}
                    rec = {
                        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        "model": orch.model, "config": cfg, "repeat": rep_i,
                        "seed": 10_000 + rep_i, "lang": lang,
                        "question": q, "session_id": sid,
                        "reply": out.get("reply"),
                        "fallback": bool(out.get("fallback")),   # Mock'a düşenler dışlanır
                        "provenance": out.get("provenance"),
                        "reference_check": ref_check,
                        "legacy_guard": out.get("guard"),
                        "simulation_result_keys": sorted((out.get("simulation_result") or {}).keys()),
                        # A23: son PV araç-sonucunun ışınım kaynağı (pvgis_tmy_cache | clearsky)
                        "irradiance_source": (out.get("simulation_result") or {}).get(
                            "irradiance_source"),
                        "wall_s": round(time.time() - t0, 2),
                        "error": error,
                        **run_env,
                    }
                    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    fh.flush()
                    print(f"[{cfg} r{rep_i}] {q['id']}: "
                          f"{'ERR ' + error if error else ('FALLBACK' if rec['fallback'] else 'ok')} "
                          f"({rec['wall_s']}s)")

    oo.SIMULATION_TOOLS = orig_tools
    if expect_env is not None:                      # A21-E5: koşu sonu drift denetimi
        try:
            _checked_environment(model_name, reference, "bitiş")
        except EnvDrift as exc:
            exc.path = out_path
            raise
    print(f"\nHam izler: {out_path}")
    return out_path


def _stk(bench_stakeholder: str) -> str:
    # benchmark etiketi → API stakeholder_type
    return {"residential": "residential", "commercial": "commercial",
            "distribution": "utility", "state": "utility"}.get(bench_stakeholder,
                                                               "residential")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=None, help="Ollama model adı (vars: settings)")
    ap.add_argument("--configs", default="grounded_guard,grounded_noguard,ungrounded")
    ap.add_argument("--limit", type=int, default=None, help="ilk N soru (smoke için)")
    ap.add_argument("--repeats", type=int, default=1, help="hücre başına tekrar (A2: 3)")
    ap.add_argument("--lang", default="tr", choices=["tr", "en"],
                    help="soru dili (cross-lingual koşul, prereg-v2.0)")
    a = ap.parse_args()
    run(a.model, [c.strip() for c in a.configs.split(",") if c.strip()], a.limit,
        repeats=a.repeats, lang=a.lang)
