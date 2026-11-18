"""A8 precision-coding paketi üreticisi.

Bloklu (grounded_guard, provenance.blocked=True) G1 yanıtlarını, 2 bağımsız
insan kodlayıcının guard'ın etiketine BAKMADAN (körleme) değerlendireceği bir
kodlama sayfasına çıkarır. Amaç: guard'ın canlı-koşu blok kararlarının
PRECISION'ı (gerçek-pozitif blok mu, yoksa over-block mu?) + Cohen's κ.

Üretilenler (a8_precision/ altına):
  A8_coding_sheet.csv  — KÖR sayfa: coding_id, meta, ham (pre-intervention) yanıt,
                          referans yer-gerçeği sayıları + BOŞ kodlayıcı sütunları.
                          Guard'ın kararı/etiketi YOK (körleme).
  A8_guard_key.csv     — Kodlayıcılara GÖSTERİLMEZ: guard'ın müdahale-öncesi
                          ihlal sayıları (kodlama bitince karşılaştırma/adjudication).

Kullanım (container içinde):
  python -m experiments.gfp_benchmark.make_a8_package
"""
from __future__ import annotations
import csv
import glob
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
OUT = HERE / "a8_precision"


def _latest(pattern: str) -> Path | None:
    hits = sorted(glob.glob(str(RESULTS / pattern)))
    return Path(hits[-1]) if hits else None


def _ref_numbers(question: dict, ref_orch) -> str:
    """Soru için KOL-BAĞIMSIZ tam-zincir referans grafından yer-gerçeği sayıları.
    Kodlayıcı, ham yanıttaki her sayıyı bu listeye karşı bağımsız yargılar."""
    from experiments.gfp_benchmark.run_benchmark import _reference_graph
    g, ok, reason = _reference_graph(question, ref_orch)
    if not ok:
        return f"[REFERANS KURULAMADI: {reason}]"
    lines = []
    for d in g.records_as_dicts():
        val = d.get("value")
        unit = d.get("unit") or ""
        scale = d.get("scale") or "?"
        src = d.get("source_function") or "?"
        key = d.get("key") or "?"
        lines.append(f"{key} = {val:,.4g} {unit}  [ölçek={scale}, kaynak={src}]")
    # tekilleştir (zincirlerde aynı key farklı ölçekte tekrar edebilir → hepsini tut)
    return "\n".join(dict.fromkeys(lines))


def main() -> None:
    OUT.mkdir(exist_ok=True)
    from app.llm import ollama_orchestrator as oo

    files = []
    for pat in ("raw_g1_gemma4-e4b_2026070*.jsonl", "raw_g1_qwen3.5-27b_2026070*.jsonl"):
        f = _latest(pat)
        if f:
            files.append(f)
    if not files:
        raise SystemExit("results/ altında G1 ham dosyası bulunamadı")

    blocked = []
    for f in files:
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            prov = r.get("provenance") or {}
            if prov.get("blocked"):
                blocked.append(r)
    print(f"bloklu yanıt: {len(blocked)}  ({[f.name for f in files]})")

    ref_orch = oo.OllamaOrchestrator()
    ref_cache: dict[str, str] = {}

    blind_rows = []
    key_rows = []
    for i, r in enumerate(sorted(blocked, key=lambda x: (x["model"], x["question"]["id"], x["repeat"])), 1):
        q = r["question"]
        qid = q["id"]
        if qid not in ref_cache:
            ref_cache[qid] = _ref_numbers(q, ref_orch)
        prov = r["provenance"]
        pre = prov.get("pre_intervention") or {}
        raw_reply = pre.get("reply") or ""
        cid = f"A8-{i:03d}"

        blind_rows.append({
            "coding_id": cid,
            "model": r["model"],
            "qid": qid,
            "stakeholder": q.get("stakeholder", ""),
            "scale_focus": q.get("scale_focus", ""),
            "chain_length": q.get("chain_length", ""),
            "difficulty": q.get("difficulty", ""),
            "question_tr": q.get("question_tr", ""),
            "raw_reply": raw_reply,
            "reference_numbers": ref_cache[qid],
            # --- KODLAYICI DOLDURUR (boş) ---
            "n_numeric_claims": "",
            "n_genuine_violations": "",
            "violation_types": "",
            "block_justified_YN": "",
            "coder_notes": "",
        })

        pc = pre.get("counts") or {}
        key_rows.append({
            "coding_id": cid,
            "model": r["model"],
            "qid": qid,
            "repeat": r["repeat"],
            "guard_blocked": True,
            "guard_retried": prov.get("retried"),
            "pre_UNGROUNDED": pc.get("UNGROUNDED", 0),
            "pre_SCALE_VIOLATION": pc.get("SCALE_VIOLATION", 0),
            "pre_UNIT_MISMATCH": pc.get("UNIT_MISMATCH", 0),
            "pre_GROUNDED": pc.get("GROUNDED", 0),
            "ambiguous": (pre.get("ambiguous_matches")),
        })

    blind_cols = list(blind_rows[0].keys())
    with (OUT / "A8_coding_sheet.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=blind_cols)
        w.writeheader()
        w.writerows(blind_rows)

    key_cols = list(key_rows[0].keys())
    with (OUT / "A8_guard_key.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=key_cols)
        w.writeheader()
        w.writerows(key_rows)

    # özet
    from collections import Counter
    mc = Counter(r["model"] for r in blocked)
    print(f"yazıldı: {OUT/'A8_coding_sheet.csv'} ({len(blind_rows)} satır)")
    print(f"yazıldı: {OUT/'A8_guard_key.csv'}")
    print(f"model dağılımı: {dict(mc)}")
    print(f"benzersiz soru (referans kurulan): {len(ref_cache)}")
    fails = [k for k, v in ref_cache.items() if v.startswith('[REFERANS')]
    if fails:
        print(f"UYARI referans kurulamayan qid: {fails}")


if __name__ == "__main__":
    main()
