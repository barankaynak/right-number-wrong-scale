"""A21(h)(ii) / E4(ii) — determinizm yeniden-koşusunun özdeşlik raporu [POST-OUTCOME hesap, metrik
ön-kayıtlı]. A21(h)(ii) her koşul bitince 5 sabit hücreyi (res-01, com-01, dis-01, sta-01, res-11;
seed 10000; grounded_noguard) ayrı `determinism_check_*.jsonl` dosyasına yeniden koşturdu; karşılaştıran
donmuş betik yoktu. Bu betik yalnız o karşılaştırmayı yapar: her determinizm hücresinin metni, ana
koşunun aynı (qid, grounded_noguard, repeat 0 = seed 10000) satırıyla; metrik E4(i) ile aynı — tam
eşitlik ve SequenceMatcher ≥ 0.95, `guard_coverage.py`'nin metin seçimiyle (pre_intervention.reply,
yoksa reply). LLM/simülatör çağrısı yok; yalnız iz okur.
Kullanım: GFP_RUN_DIR=oct_v42 python -m experiments.gfp_benchmark.determinism_identity
"""
from __future__ import annotations

import json
from difflib import SequenceMatcher

from experiments.gfp_benchmark.rescore_crosslingual import FILE_GLOBS, RESULTS, _latest, _pre_reply


def _rows(path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _text(rec: dict) -> str:
    return _pre_reply(rec) or rec.get("reply") or ""


def main() -> None:
    out = {}
    for (lang, model), pattern in FILE_GLOBS.items():
        main_f = _latest(pattern)
        det_f = _latest(pattern.replace("raw_g1_", "determinism_check_", 1))
        if not (main_f and det_f):
            out[f"{lang}|{model}"] = {"status": "not run"}
            continue
        base = {r["question"]["id"]: r for r in _rows(main_f)
                if r.get("config") == "grounded_noguard" and r.get("repeat") == 0}
        cells = []
        for d in _rows(det_f):
            b = base.get(d["question"]["id"])
            excluded = any(x.get("fallback") or x.get("error") for x in (d, b) if x)
            if b is None or excluded:
                cells.append({"qid": d["question"]["id"], "status": "excluded"})
                continue
            x, y = _text(d), _text(b)
            cells.append({"qid": d["question"]["id"], "identical": x == y,
                          "similar_ge_0_95": SequenceMatcher(None, x, y).ratio() >= 0.95,
                          "seed_det": d.get("seed"), "seed_main": b.get("seed")})
        ok = [c for c in cells if "identical" in c]
        out[f"{lang}|{model}"] = {"main_file": main_f.name, "det_file": det_f.name, "n": len(ok),
                                  "identical": sum(c["identical"] for c in ok),
                                  "similar_ge_0_95": sum(c["similar_ge_0_95"] for c in ok),
                                  "cells": cells}
        print(f"{lang} {model:22s} identical {out[f'{lang}|{model}']['identical']}/{len(ok)}  "
              f"similar>=0.95 {out[f'{lang}|{model}']['similar_ge_0_95']}/{len(ok)}")
    p = RESULTS / "determinism_identity.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"-> {p}")


if __name__ == "__main__":
    main()
