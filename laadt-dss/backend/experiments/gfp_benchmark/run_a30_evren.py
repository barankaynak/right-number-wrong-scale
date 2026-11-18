"""A30 — EVREN (uzak, büyük açık-ağırlıklı modeller) keşifsel ölçek denetimi [PRE-RUN taslak].

Donmuş G1 (`run_benchmark.run`) ve G1-MT (`run_multiturn.run_mt`) sürücüleri DEĞİŞTİRİLMEDEN
çağrılır; bu süreçte (ayrı `docker exec`, koşan deneyleri etkilemez) yalnız iki şey yerine konur:
  1) `OllamaOrchestrator._call_ollama` → EVREN OpenAI-uyumlu /v1/chat/completions taşıması
  2) `run_benchmark._run_environment` → EVREN model kartı kimliği (Ollama digest'i yok)
Kol yapılandırması, seed (10000+tekrar), sıcaklık 0.3, sistem promptu, araç şemaları, referans
graflar, dışlama (%10) ve deneme (2) kuralları G1/G1-MT ile aynıdır. Isınma yok (uzak sunucu).
Anahtar yalnız EVREN_API_KEY ortam değişkeninden okunur; hiçbir dosyaya/loga yazılmaz.

Kullanım (konteynerde; `run` G1-MT BİTTİKTEN SONRA — simülasyon motoru ortak):
    GFP_RUN_DIR=oct_v42_evren EVREN_API_KEY=... python -m experiments.gfp_benchmark.run_a30_evren run
    EVREN_API_KEY=... python -m experiments.gfp_benchmark.run_a30_evren smoke <çıktı.json> <m1,m2> <default|off>
        (yalnız taşıma denetimi: sahte araç sonucu, simülasyon motoruna dokunmaz)
Log: results/<GFP_RUN_DIR>/a30_log.jsonl ; çağrı telemetrisi: a30_calls.jsonl
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
import time
from datetime import datetime, timezone

import httpx

from experiments.gfp_benchmark import run_benchmark as rb
from experiments.gfp_benchmark.run_g1_rerun import ARMS, DET_QIDS, EXCL_LIMIT, MAX_ATTEMPTS, REPEATS

BASE = os.environ.get("EVREN_BASE_URL", "")  # OpenAI-compatible endpoint of the hosted model
MODELS = ["deepseek-v4.1-flash"]    # glm-5.3 kapasite, qwen3.8-flash-next system-rolü nedeniyle elendi
LANG = "tr"
EXPERIMENTS = ["g1", "mt"]          # sıra: önce G1 (+ determinizm), sonra G1-MT
TEMPERATURE = 0.3                   # = OllamaOrchestrator._call_ollama
TIMEOUT_S = 600                     # çağrı başına (yerelde OLLAMA_TIMEOUT=60; uzak + düşünme;
                                    # duman testinde en uzun çağrı 237 s)
# Üretim BAŞLAMADAN reddedilen istekler (503 kapasite, 429 eşzamanlılık/hız, bağlantı kurulamadı)
# beklenip yeniden gönderilir: model henüz hiçbir şey üretmemiştir. Çağrı başına en çok
# CAPACITY_WAIT_MAX_S; aşılırsa satır G1'deki gibi fallback/dışlama olur. Üretim sırasında
# kopan istek (okuma zaman aşımı, 500/502/504, diğer 4xx) G1'deki zaman aşımı gibi YENİDEN
# DENENMEZ → fallback (dışlama).
CAPACITY_WAIT_MAX_S = 1800
MAX_DAILY_WAITS = 2                 # günlük kota dolarsa sıfırlanmaya kadar bekle (en çok 2 kez)
THINKING: bool | None = None        # None = sağlayıcı varsayılanı (yerelde de `think` verilmedi)

_CTX = threading.local()
_HTTP: httpx.Client | None = None


def _key() -> str:
    k = os.environ.get("EVREN_API_KEY", "").strip()
    if not k:
        sys.exit("EVREN_API_KEY tanımlı değil")
    return k


def _http() -> httpx.Client:
    global _HTTP
    if _HTTP is None:
        _HTTP = httpx.Client(headers={"X-API-Key": _key()}, timeout=TIMEOUT_S)
    return _HTTP


def _append(name: str, event: dict) -> None:
    event = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), **event}
    rb.RESULTS.mkdir(parents=True, exist_ok=True)
    with (rb.RESULTS / name).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")


def _log(event: dict) -> None:
    print(f"[A30] {event}", flush=True)
    _append("a30_log.jsonl", event)


def _get(path: str) -> dict:
    r = _http().get(f"{BASE}{path}", timeout=30)
    r.raise_for_status()
    return r.json()


def _wait_daily_reset() -> None:
    reset = datetime.fromisoformat(_get("/quota")["daily_reset_at"].replace("Z", "+00:00"))
    wait = max(60.0, (reset - datetime.now(timezone.utc)).total_seconds() + 120)
    _log({"event": "daily_quota_wait", "until": reset.isoformat(), "s": round(wait)})
    time.sleep(wait)


# ---------------------------------------------------------------------------
# Taşıma: Ollama /api/chat ↔ OpenAI /v1/chat/completions
# ---------------------------------------------------------------------------

def _to_openai(messages: list[dict]) -> list[dict]:
    """Orkestratör geçmişini OpenAI şemasına çevirir: araç mesajlarına, önceki asistan
    mesajının tool_calls kimlikleri SIRAYLA eşlenir (orkestratör tool_call_id yazmaz)."""
    out, pending = [], []
    for i, m in enumerate(messages):
        m = dict(m)
        if m.get("role") == "assistant" and m.get("tool_calls"):
            calls = []
            for j, tc in enumerate(m["tool_calls"]):
                fn = tc.get("function") or {}
                args = fn.get("arguments", {})
                calls.append({"id": tc.get("id") or f"call_{i}_{j}", "type": "function",
                              "function": {"name": fn.get("name", ""),
                                           "arguments": args if isinstance(args, str)
                                           else json.dumps(args, ensure_ascii=False)}})
            m["tool_calls"], m["content"] = calls, m.get("content") or ""
            pending = [c["id"] for c in calls]
        elif m.get("role") == "tool":
            m.pop("name", None)
            m["tool_call_id"] = pending.pop(0) if pending else f"call_orphan_{i}"
        out.append(m)
    return out


def _post(payload: dict) -> tuple[dict, int, float]:
    """Dönen: (yanıt, bekleme sayısı, son isteğin süresi). Kurallar: CAPACITY_WAIT_MAX_S notu."""
    start, waits, daily_waits = time.time(), 0, 0
    while True:
        t0 = time.time()
        try:
            r = _http().post(f"{BASE}/chat/completions", json=payload)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout) as exc:
            last, wait = repr(exc), 20.0              # bağlantı kurulamadı: üretim başlamadı
        else:                                         # okuma zaman aşımı vb. → yukarı (fallback)
            if r.status_code == 200:
                return r.json(), waits, round(time.time() - t0, 2)
            try:
                code = (r.json().get("error") or {}).get("code")
            except ValueError:
                code = None
            last = f"HTTP {r.status_code} {code}"
            if r.status_code == 429 and code == "daily_token_limit_exceeded":
                if daily_waits >= MAX_DAILY_WAITS:
                    raise RuntimeError(last)
                daily_waits += 1
                _wait_daily_reset()
                start = time.time()
                continue
            if r.status_code not in (429, 503):
                raise RuntimeError(f"{last}: {r.text[:300]}")
            wait = float(r.headers.get("Retry-After") or 20.0)
        if time.time() + wait - start > CAPACITY_WAIT_MAX_S:
            raise RuntimeError(f"kapasite beklemesi {CAPACITY_WAIT_MAX_S} s'yi aştı: {last}")
        _append("a30_calls.jsonl", {"event": "capacity_wait", "sid": getattr(_CTX, "sid", None),
                                    "n": waits, "reason": last, "wait_s": wait})
        time.sleep(wait)
        waits += 1


def _evren_call(self, messages: list[dict], stakeholder_type: str = "residential") -> dict:
    """`OllamaOrchestrator._call_ollama` yerine: aynı sistem promptu, araçlar, sıcaklık, seed."""
    from app.llm import ollama_orchestrator as oo
    system_prompt = oo.get_system_prompt(stakeholder_type, getattr(self, "_lang", "tr"))
    payload = {"model": self.model, "temperature": TEMPERATURE, "stream": False,
               "messages": _to_openai([{"role": "system", "content": system_prompt}] + messages)}
    if oo.SIMULATION_TOOLS:                           # ungrounded kol: araç alanı hiç gönderilmez
        payload["tools"] = oo.SIMULATION_TOOLS
    seed = getattr(self, "_ollama_seed", None)
    if seed is not None:
        payload["seed"] = int(seed)
    if THINKING is not None:
        payload["thinking"] = THINKING
    data, retries, wall = _post(payload)
    choice = (data.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    _append("a30_calls.jsonl", {
        "event": "call", "sid": getattr(_CTX, "sid", None), "model": self.model,
        "served_model": data.get("model"), "finish_reason": choice.get("finish_reason"),
        "usage": data.get("usage"), "capacity_waits": retries, "wall_s": wall,
        "n_tool_calls": len(msg.get("tool_calls") or []),
        "had_reasoning": bool(msg.get("reasoning") or msg.get("reasoning_content"))})
    if choice.get("finish_reason") == "length":       # bütçe düşünmede tükendi → fallback sayılır
        raise RuntimeError("finish_reason=length")
    out = {"role": "assistant", "content": msg.get("content") or ""}
    if msg.get("tool_calls"):
        out["tool_calls"] = [{"id": tc.get("id"), "type": "function",
                              "function": {"name": (tc.get("function") or {}).get("name", ""),
                                           "arguments": (tc.get("function") or {}).get(
                                               "arguments") or "{}"}}
                             for tc in msg["tool_calls"]]
    return out


def _evren_environment(model_name: str) -> dict:
    """`run_benchmark._run_environment` yerine. Ollama digest'i yerine: model kartının
    (`created` hariç — sunucu her istekte değiştiriyor) SHA-256'sı. Kimlik anahtarı
    (`ollama_version`, `model_digest`) = ("evren-gateway", kart hash'i); şartlar sürümü ayrı
    alanda kaydedilir (kozmetik şart sürümü sapma sayılmaz). Sunucuya ulaşılamaması model
    değişimi değildir: GET'ler CAPACITY_WAIT_MAX_S boyunca beklenerek yeniden denenir, ancak
    sonra kimlik None döner."""
    app_dir = rb.HERE.parent.parent / "app"
    env = {"ollama_version": None, "model_digest": None,
           "guard_sha256": hashlib.sha256(
               (app_dir / "llm" / "provenance_guard.py").read_bytes()).hexdigest(),
           "tmy_manifest_sha256": hashlib.sha256(
               (app_dir / "simulation" / "pv" / "tmy_cache" / "MANIFEST.json").read_bytes()
           ).hexdigest()}
    start, wait = time.time(), 10.0
    while True:
        try:
            card = _get(f"/models/{model_name}")
            terms = _get("/terms/status")
            break
        except Exception as exc:
            if time.time() + wait - start > CAPACITY_WAIT_MAX_S:
                env["env_error"] = repr(exc)          # kimlik alınamazsa iz bırakır
                return env
            _append("a30_calls.jsonl", {"event": "identity_wait", "reason": repr(exc)[:200],
                                        "wait_s": wait})
            time.sleep(wait)
            wait = min(120.0, wait * 2)
    card.pop("created", None)
    env["ollama_version"] = "evren-gateway"
    env["model_digest"] = hashlib.sha256(json.dumps(card, sort_keys=True).encode()).hexdigest()
    env["evren_card"] = card
    env["evren_terms_version"] = terms.get("current_version")
    return env


def _install() -> None:
    from app.llm import ollama_orchestrator as oo
    orig_pm = oo.OllamaOrchestrator.process_message

    def process_message(self, message, session_id, *a, **kw):   # telemetri için oturum kimliği
        _CTX.sid = session_id
        return orig_pm(self, message, session_id, *a, **kw)

    oo.OllamaOrchestrator._call_ollama = _evren_call
    oo.OllamaOrchestrator.process_message = process_message
    rb._run_environment = _evren_environment


# ---------------------------------------------------------------------------
# Koşu
# ---------------------------------------------------------------------------

def _exclusion_rate(path) -> tuple[int, int, float]:
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    excl = sum(1 for r in rows if r.get("fallback") or r.get("error"))
    return len(rows), excl, (excl / len(rows) if rows else 1.0)


def _archive(path, reason: str) -> None:
    if path is not None and path.exists():
        dst = path.with_name("aborted_" + path.name)
        path.rename(dst)
        _log({"event": "archived", "file": dst.name, "reason": reason})


def main_run() -> None:
    _install()
    from experiments.gfp_benchmark.run_multiturn import run_mt
    rb.RESULTS.mkdir(parents=True, exist_ok=True)
    _log({"event": "start", "models": MODELS, "lang": LANG, "experiments": EXPERIMENTS,
          "repeats": REPEATS, "timeout_s": TIMEOUT_S})
    for exp in EXPERIMENTS:
        for model in MODELS:
            # A30: sabitlenmiş tablo yok → kimlik koşul başında alınır; koşul içi sapma iptal
            expect = rb._env_key(rb._run_environment(model))
            status = "not run"
            for attempt in range(1, MAX_ATTEMPTS + 1):
                t0 = time.time()
                _log({"event": "condition_start", "exp": exp, "model": model,
                      "attempt": attempt, "identity": expect})
                try:
                    if exp == "g1":
                        path = rb.run(model, ARMS, None, session_prefix="a30", repeats=REPEATS,
                                      lang=LANG, expect_env=expect)
                    else:
                        path = run_mt(model, LANG, expect)
                except rb.EnvDrift as exc:
                    if exc.path is None:
                        _log({"event": "stop_env_mismatch_at_start", "exp": exp,
                              "model": model, "reason": str(exc)})
                        break
                    _archive(exc.path, f"env drift: {exc}")
                    expect = rb._env_key(rb._run_environment(model))
                    continue
                n, excl, rate = _exclusion_rate(path)
                _log({"event": "condition_done", "exp": exp, "model": model, "file": path.name,
                      "n": n, "excluded": excl, "excl_rate": round(rate, 4),
                      "wall_h": round((time.time() - t0) / 3600, 2)})
                if rate > EXCL_LIMIT:
                    _archive(path, f"exclusion rate {rate:.3f} > {EXCL_LIMIT}")
                    continue
                status = "complete"
                break
            _log({"event": "condition_status", "exp": exp, "model": model, "status": status})
            if exp == "g1" and status == "complete":   # G1 ile aynı 5-hücre determinizm denetimi
                try:
                    det = rb.run(model, ["grounded_noguard"], None, session_prefix="a30det",
                                 repeats=1, lang=LANG, qids=DET_QIDS,
                                 file_prefix="determinism_check", expect_env=expect)
                    _log({"event": "determinism_check_done", "model": model, "file": det.name})
                except rb.EnvDrift as exc:
                    _archive(exc.path, f"env drift during determinism check: {exc}")
    _log({"event": "end"})


# ---------------------------------------------------------------------------
# Duman testi (yalnız taşıma; simülasyon motoruna DOKUNMAZ)
# ---------------------------------------------------------------------------

def main_smoke(out_file: str, models: list[str], thinking: bool | None) -> None:
    global THINKING
    THINKING = thinking
    from app.llm import ollama_orchestrator as oo
    qs = {q["id"]: q for q in rb._load_questions(None)}
    q = qs["res-01"]
    fake_tool = {"status": "smoke_fake", "annual_production_kwh": 1234.5, "payback_years": 6.7}

    class _O:                                          # orkestratör yerine geçen en küçük nesne
        _lang = LANG

    def step(r, name, fn):
        t0 = time.time()
        try:
            r[name] = {"ok": True, **fn(), "s": round(time.time() - t0, 1)}
        except Exception as exc:
            r[name] = {"ok": False, "error": repr(exc)[:200], "s": round(time.time() - t0, 1)}
        print(f"[smoke] {o.model} {name}: {r[name]}", flush=True)
        return r[name]["ok"]

    report = {"thinking": thinking}
    for model in models:
        o = _O()
        o.model, o._ollama_seed = model, 10_000
        r: dict = {"identity": _evren_environment(model).get("model_digest")}
        hist = [{"role": "user", "content": q["question_tr"]}]
        a = {}

        def t1():
            a[1] = _evren_call(o, hist, "residential")
            return {"tool_calls": [tc["function"]["name"] for tc in a[1].get("tool_calls") or []]}

        def t2():
            if a[1].get("tool_calls"):
                hist.append({"role": "assistant", "content": a[1]["content"],
                             "tool_calls": a[1]["tool_calls"]})
                for tc in a[1]["tool_calls"]:
                    hist.append({"role": "tool", "name": tc["function"]["name"],
                                 "content": json.dumps(fake_tool)})
            a[2] = _evren_call(o, hist, "residential")
            hist.append({"role": "assistant", "content": a[2]["content"]})
            return {"content_chars": len(a[2]["content"])}

        def midconv():                                 # guard düzeltme yolu: ortada system mesajı
            hist.append({"role": "system", "content": "Yanıtındaki sayıların yalnız araç "
                         "çıktısından gelmesi gerekir; yanıtı buna göre yeniden yaz."})
            return {"content_chars": len(_evren_call(o, hist, "residential")["content"])}

        def ungrounded():                              # araç alanı hiç gönderilmez
            saved, oo.SIMULATION_TOOLS = oo.SIMULATION_TOOLS, []
            try:
                c = _evren_call(o, [{"role": "user", "content": q["question_tr"]}], "residential")
            finally:
                oo.SIMULATION_TOOLS = saved
            return {"content_chars": len(c["content"])}

        def seed_repeat():                             # aynı ilk çağrı yeniden
            b = _evren_call(o, [{"role": "user", "content": q["question_tr"]}], "residential")
            return {"same": json.dumps(b, sort_keys=True, ensure_ascii=False)
                    == json.dumps(a[1], sort_keys=True, ensure_ascii=False)}

        if step(r, "t1", t1):
            step(r, "t2", t2) and step(r, "midconv_system", midconv)
            step(r, "seed_repeat", seed_repeat)
        step(r, "ungrounded", ungrounded)
        report[model] = r
    with open(out_file, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "run":
        main_run()
    elif len(sys.argv) >= 5 and sys.argv[1] == "smoke":   # smoke <çıktı> <m1,m2> <default|off>
        main_smoke(sys.argv[2], sys.argv[3].split(","), None if sys.argv[4] == "default" else False)
    else:
        sys.exit(__doc__)
