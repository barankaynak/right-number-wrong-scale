"""G1 tam yeniden-koşusu sürücüsü — A21/A23/A24 [PRE-RUN, prereg-v3.1], guard v4.2.

7 koşul (A24) × 3 kol × 56 soru × 3 tekrar, sıralı; A21-E5 kuralları:
  - başlangıçta, her (kol, tekrar) başında ve sonda Ollama sürümü + model digest'i A21
    tablosuyla doğrulanır; koşu-içi sapma → o KOŞULUN 3 kolu birlikte iptal
    (`aborted_*` arşiv) ve baştan; A21 tablosuyla başlangıç uyuşmazlığı → sürücü DURUR
    (kalan koşullar "not run"; Temmuz verisiyle doldurulmaz).
  - fallback+error > %10 (A2) → koşul geçersiz → `aborted_*` + baştan.
  - hücre-düzeyi yama yok; en çok MAX_ATTEMPTS deneme, sonra "not run".
  - ara-bakış yok: yalnız iz sayısı / fallback / error / süre loglanır (GFS hesaplanmaz).
A21-E4(ii): her tamamlanan koşuldan sonra 5 sabit hücre (seed 10000, grounded_noguard)
ayrı dosyaya (`determinism_check_*.jsonl`) yeniden koşulur.

Kullanım (konteynerde, detached):
    GFP_RUN_DIR=oct_v42 python -m experiments.gfp_benchmark.run_g1_rerun
Log: results/<GFP_RUN_DIR>/rerun_log.jsonl
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from experiments.gfp_benchmark.run_benchmark import RESULTS, EnvDrift, run

OLLAMA_VERSION = "0.34.3"
DIGESTS = {   # A21 + A24 ortam tablosu (tag'den önce doğrulandı)
    "gemma4:e4b": "c6eb396dbd5992bbe3f5cdb947e8bbc0ee413d7c17e2beaae69f5d569cf982eb",
    "qwen3.8:27b": "aaee06c39dcf2437cde036998d960e1fc1494b8191be7cc9657d01e509097813",
    "mistral-small3.2:24b": "5a408ab55df5c1b5cf46533c368813b30bf9e4d8fc39263bf2a3338cfa3b895b",
    "glm-4.7-flash:latest": "4475827791a269b02c8ec49b1c3bc1abb5846bacf3fae015b75d33986322d8f6",
    "muse-glimmer:30b": "de878ce33ad81d060001db1469a02eebe4d86f0ad58cfe52dc062fdcbe4464c1",
}
# A24 sırası: ön-kayıtlı çekirdek önce (A-TR, B-TR, A-EN, B-EN), sonra C, D, E
CONDITIONS = [("gemma4:e4b", "tr"), ("qwen3.8:27b", "tr"), ("gemma4:e4b", "en"),
              ("qwen3.8:27b", "en"), ("mistral-small3.2:24b", "tr"),
              ("glm-4.7-flash:latest", "tr"), ("muse-glimmer:30b", "tr")]
ARMS = ["grounded_guard", "grounded_noguard", "ungrounded"]
REPEATS = 3
DET_QIDS = ["res-01", "com-01", "dis-01", "sta-01", "res-11"]
MAX_ATTEMPTS = 2
EXCL_LIMIT = 0.10


def _log(event: dict) -> None:
    event = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), **event}
    print(f"[RERUN] {event}", flush=True)
    with (RESULTS / "rerun_log.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")


def _archive(path, reason: str) -> None:
    if path is not None and path.exists():
        dst = path.with_name("aborted_" + path.name)
        path.rename(dst)
        _log({"event": "archived", "file": dst.name, "reason": reason})


def _warm_up(model: str, lang: str) -> None:
    """A27: koşul başlamadan modeli belleğe yükler ve sistem-prompt + araç önekini bir
    kez işletir (tek token, benchmark dışı mesaj). Sunucu tek model tutar; yükleme
    sonrası İLK istek önek-önbelleği boşken işlenir ve GLM'de res-01 ilk istek olunca
    üretim 60/120/300 s zaman aşımlarını aştı (aynı hücre önekli durumda ≈10 s). Isınma
    ile her benchmark hücresi aynı (önekli) önbellek durumunda başlar."""
    import httpx
    from app.core.config import settings
    from app.llm.ollama_orchestrator import SIMULATION_TOOLS
    from app.llm.prompts.stakeholder_prompts import get_system_prompt
    t0 = time.time()
    try:
        httpx.post(f"{settings.OLLAMA_HOST}/api/chat", timeout=900, json={
            "model": model, "stream": False, "keep_alive": "30m", "tools": SIMULATION_TOOLS,
            "messages": [{"role": "system", "content": get_system_prompt("residential", lang)},
                         {"role": "user", "content": "Merhaba" if lang == "tr" else "Hello"}],
            "options": {"num_predict": 1, "temperature": 0.0},
        }).raise_for_status()
        _log({"event": "warm_up", "model": model, "lang": lang, "s": round(time.time() - t0, 1)})
    except Exception as exc:                  # ısınma başarısızsa koşu yine başlar
        _log({"event": "warm_up_failed", "model": model, "reason": repr(exc)})


def _exclusion_rate(path) -> tuple[int, int, float]:
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    excl = sum(1 for r in rows if r.get("fallback") or r.get("error"))
    return len(rows), excl, (excl / len(rows) if rows else 1.0)


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    _log({"event": "start", "conditions": CONDITIONS, "repeats": REPEATS})
    for model, lang in CONDITIONS:
        expect = (OLLAMA_VERSION, DIGESTS[model])
        status = "not run"
        for attempt in range(1, MAX_ATTEMPTS + 1):
            _warm_up(model, lang)
            t0 = time.time()
            _log({"event": "condition_start", "model": model, "lang": lang, "attempt": attempt})
            try:
                path = run(model, ARMS, None, repeats=REPEATS, lang=lang, expect_env=expect)
            except EnvDrift as exc:
                if exc.path is None:          # başlangıç A21 tablosuyla uyuşmuyor → DUR
                    _log({"event": "stop_env_mismatch_at_start", "model": model,
                          "lang": lang, "reason": str(exc)})
                    _log({"event": "end", "note": "kalan koşullar 'not run'"})
                    return
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
        if status != "complete":
            continue
        try:
            _warm_up(model, lang)
            det = run(model, ["grounded_noguard"], None, session_prefix="det", repeats=1,
                      lang=lang, qids=DET_QIDS, file_prefix="determinism_check",
                      expect_env=expect)
            _log({"event": "determinism_check_done", "model": model, "lang": lang,
                  "file": det.name})
        except EnvDrift as exc:
            _archive(exc.path, f"env drift during determinism check: {exc}")
    _log({"event": "end"})


if __name__ == "__main__":
    main()
