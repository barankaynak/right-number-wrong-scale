"""A9 (keşifsel) — bloklu-altküme karşı-olgusal ref-GFS.

Merkezi gerilim: guard blok oranı yüksek (qwen %52) ama toplam ref-GFS artışı
küçük (+~%2). Bu, guard'ın BLOKLADIĞI yanıtlarda müdahalenin ref-fidelity'yi ne
kadar yükselttiğini ölçerek "metrik-seyrelme" (guard blokladığı yerde çok yardım
ediyor, harekete geçmediği yerlerde ortalamaya seyreliyor) hipotezini sınar.

Her bloklu yanıt için EŞLEŞTİRİLMİŞ:
  ref-GFS(safe_summary)      = kayıttaki reference_check (final = guard müdahalesi SONRASI)
  ref-GFS(pre_intervention)  = ham LLM metni, aynı KOL-BAĞIMSIZ referans-grafiğe
                               YENİDEN-notlanır (kayıtta saklı DEĞİL → burada üretilir)

Bu ön-kayıtlı H_G1b'nin YERİNE GEÇMEZ; PREREGISTRATION §9'da exploratory (A9).
Kullanım: python -m experiments.gfp_benchmark.a9_counterfactual
"""
from __future__ import annotations
import glob
import json
import statistics as st
from pathlib import Path

from experiments.gfp_benchmark.compute_gfs import gfs_from_counts
from experiments.gfp_benchmark.run_benchmark import _reference_graph

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"


def _wilcoxon_p(diffs: list[float]) -> float | None:
    """İki-yönlü Wilcoxon signed-rank (sıfır-farklar atılır); scipy varsa onu kullan."""
    nz = [d for d in diffs if d != 0]
    if len(nz) < 1:
        return None
    try:
        from scipy.stats import wilcoxon
        return float(wilcoxon(nz).pvalue)
    except Exception:
        return None


def run() -> dict:
    from app.llm import ollama_orchestrator as oo
    files = []
    for pat in ("raw_g1_gemma4-e4b_2026070*.jsonl", "raw_g1_qwen3.5-27b_2026070*.jsonl"):
        hits = sorted(glob.glob(str(RESULTS / pat)))
        if hits:
            files.append(Path(hits[-1]))

    ref_orch = oo.OllamaOrchestrator()
    ref_cache: dict = {}

    def _graph(q):
        qid = q["id"]
        if qid not in ref_cache:
            g, ok, _ = _reference_graph(q, ref_orch)
            ref_cache[qid] = g if ok else None
        return ref_cache[qid]

    per_model: dict = {}
    for f in files:
        rows = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
        blocked = [r for r in rows if (r.get("provenance") or {}).get("blocked")]
        pairs = []          # (gfs_safe, gfs_raw)
        raw_viol = 0        # ham metinde ihlal içeren yanıt sayısı
        for r in blocked:
            g = _graph(r["question"])
            if g is None:
                continue
            safe_counts = (r.get("reference_check") or {}).get("counts")
            gfs_safe = gfs_from_counts(safe_counts)
            raw_text = ((r.get("provenance") or {}).get("pre_intervention") or {}).get("reply") or ""
            if not raw_text:
                continue
            rep = g.check_response(raw_text)
            gfs_raw = gfs_from_counts(rep.counts)
            if any(rep.counts.get(k, 0) for k in ("UNGROUNDED", "SCALE_VIOLATION", "UNIT_MISMATCH")):
                raw_viol += 1
            if gfs_safe is None or gfs_raw is None:
                continue          # notlanamayan (sayısız) yanıt eşleştirmeden düşer
            pairs.append((gfs_safe, gfs_raw))

        model = blocked[0]["model"] if blocked else f.name
        if pairs:
            safes = [a for a, _ in pairs]
            raws = [b for _, b in pairs]
            diffs = [a - b for a, b in pairs]
            per_model[model] = {
                "n_blocked": len(blocked),
                "n_paired_gradeable": len(pairs),
                "raw_with_violation": raw_viol,
                "mean_gfs_safe": round(st.mean(safes), 4),
                "mean_gfs_raw": round(st.mean(raws), 4),
                "mean_delta_safe_minus_raw": round(st.mean(diffs), 4),
                "median_delta": round(st.median(diffs), 4),
                "n_improved": sum(1 for d in diffs if d > 0),
                "n_worse": sum(1 for d in diffs if d < 0),
                "n_equal": sum(1 for d in diffs if d == 0),
                "wilcoxon_p": _wilcoxon_p(diffs),
            }
    return per_model


if __name__ == "__main__":
    out = run()
    print(json.dumps(out, ensure_ascii=False, indent=2))
