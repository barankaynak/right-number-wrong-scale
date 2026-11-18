"""A22-2 — İnsan izlenebilirlik-denetimi örneklemi ve kodlama paketi [kural PRE-RUN; çıktı
koşu sonrası]. Kodkitabı: AUDIT_CODEBOOK.md (örneklemeden ÖNCE donmuş, hash'li).

Örneklem: seed=42; tabaka = müdahale yolu × koşul; hedef P1a 40, P2 25, P0 25 (koşullara
orantılı paylaştırılır; tabaka küçükse tümü). Yalnız grounded_guard teslim metinleri.
Çıktılar (results/<GFP_RUN_DIR>/audit/):
  audit_items.jsonl   — kodlayıcı materyali: soru, referans çıktı sayfası (TR+EN biçimli),
                        numaralı teslim metni; KOL/YOL/EŞLEŞTİRİCİ KARARI YOK
  audit_sheet.csv     — kodlama sayfası (item, numara, traceable_YN, input_echo, usable_answer_YN)
  audit_key.csv       — GİZLİ anahtar: item → koşul, yol; numara → eşleştirici kararı
Kullanım: GFP_RUN_DIR=oct_v42 python -m experiments.gfp_benchmark.audit_sample
"""
from __future__ import annotations

import csv
import json
import random
from collections import defaultdict

from experiments.gfp_benchmark.intervention_paths import classify
from experiments.gfp_benchmark.rescore_crosslingual import FILE_GLOBS, _latest
from experiments.gfp_benchmark.run_benchmark import RESULTS
from experiments.gfp_benchmark.run_g4_final import _ref_graph_and_results

SEED = 42
TARGETS = {"P1a": 40, "P2": 25, "P0": 25}


def _fmt(v: float) -> tuple[str, str]:
    en = f"{v:,.4f}".rstrip("0").rstrip(".")
    tr = en.replace(",", "_").replace(".", ",").replace("_", ".")
    return tr, en


def _allocate(target: int, sizes: dict) -> dict:
    """Hedefi koşullara tabaka büyüklüğüyle orantılı dağıt (en büyük kalan yöntemi)."""
    total = sum(sizes.values())
    if total <= target:
        return dict(sizes)
    raw = {k: target * n / total for k, n in sizes.items()}
    alloc = {k: int(v) for k, v in raw.items()}
    for k in sorted(raw, key=lambda k: raw[k] - alloc[k], reverse=True)[:target - sum(alloc.values())]:
        alloc[k] += 1
    return {k: min(alloc[k], sizes[k]) for k in sizes}


def main() -> None:
    from app.llm import ollama_orchestrator as oo
    orch = oo.OllamaOrchestrator()
    rng = random.Random(SEED)
    strata = defaultdict(list)          # (path, cond) -> [rec]
    for (lang, model), pattern in FILE_GLOBS.items():
        f = _latest(pattern)
        if not f:
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("config") != "grounded_guard" or r.get("fallback") or r.get("error"):
                continue
            path = classify(r)
            if path in TARGETS:
                strata[(path, f"{lang}|{model}")].append(r)
    chosen = []
    for path, target in TARGETS.items():
        sizes = {cond: len(recs) for (p, cond), recs in strata.items() if p == path}
        for cond, k in _allocate(target, sizes).items():
            recs = sorted(strata[(path, cond)], key=lambda r: (r["question"]["id"], r.get("repeat")))
            chosen += [(path, cond, r) for r in rng.sample(recs, k)]
    rng.shuffle(chosen)

    out_dir = RESULTS / "audit"
    out_dir.mkdir(parents=True, exist_ok=True)
    graphs: dict = {}
    with (out_dir / "audit_items.jsonl").open("w", encoding="utf-8") as fi, \
         (out_dir / "audit_sheet.csv").open("w", encoding="utf-8", newline="") as fs, \
         (out_dir / "audit_key.csv").open("w", encoding="utf-8", newline="") as fk:
        sheet = csv.writer(fs)
        key = csv.writer(fk)
        sheet.writerow(["item", "number", "shown_value", "traceable_YN", "input_echo",
                        "usable_answer_YN"])
        key.writerow(["item", "number", "condition", "path", "matcher_verdict"])
        for i, (path, cond, r) in enumerate(chosen, 1):
            q = r["question"]
            if q["id"] not in graphs:
                graphs[q["id"]] = _ref_graph_and_results(q, orch)[0]
            g = graphs[q["id"]]
            lang = r.get("lang", "tr")
            text = r.get("reply") or ""
            claims = g.check_response(text).claims if g is not None else []
            sheet_rows = []
            for d in (g.records_as_dicts() if g is not None else []):
                if isinstance(d.get("value"), (int, float)):
                    tr, en = _fmt(float(d["value"]))
                    sheet_rows.append({"field": d["key"], "value_tr": tr, "value_en": en,
                                       "unit": d.get("unit") or ""})
            marked, cursor = [], 0
            numbered = text
            for n, c in enumerate(claims, 1):
                pos = numbered.find(c.text, cursor)
                if pos >= 0:
                    tag = f"{c.text} [#{n}]"
                    numbered = numbered[:pos] + tag + numbered[pos + len(c.text):]
                    cursor = pos + len(tag)
                marked.append((n, c))
            item_id = f"A{i:03d}"
            fi.write(json.dumps({"item": item_id,
                                 "question": q["question_en"] if lang == "en" else q["question_tr"],
                                 "reference_sheet": sheet_rows,
                                 "delivered_numbered": numbered}, ensure_ascii=False) + "\n")
            for n, c in marked:
                sheet.writerow([item_id, n, c.text, "", "", "" if n > 1 else ""])
                key.writerow([item_id, n, cond, path, c.verdict])
            if not marked:
                sheet.writerow([item_id, 0, "", "", "", ""])
                key.writerow([item_id, 0, cond, path, "NO_NUMBERS"])
    print(f"{len(chosen)} öğe -> {out_dir}")


if __name__ == "__main__":
    main()
