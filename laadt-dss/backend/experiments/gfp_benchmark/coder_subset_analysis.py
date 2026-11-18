"""A29-3/A29-5 — A26 kısmi çift kodlama sarmalayıcısı. Donmuş `scale_assertion_analysis` DEĞİŞMEZ.

Yazıldı ve hash'lendi: kodlayıcı dosyaları hash'lenmeden ÖNCE.
1. Tahminler: donmuş `analyze(c1, c1, consensus=c1)` çağrılır. Böylece donmuş kod, kodlayıcı-1
   etiketlerini tek etiket seti olarak 263 cümlenin tümünde kullanır. Çıktıdaki "consensus" adı
   "coder1" olarak yeniden adlandırılır. Donmuş çağrının ham çıktısı ayrıca saklanır.
2. Güvenilirlik: değişken başına κ + ham uyum + PABAK, `coder2_subset.json` boyut "80"
   örtüşmesinde (donmuş `_kappa`, `_read_coding`).
3. Örtüşmede, kodlayıcı-1 etiketinin katı (AND) / gevşek (OR) etiketten farklı olduğu cümle
   sayıları, değişken başına.
4. Jev κ-kapısı (donmuş tanım, örtüşmede): kapı değişkeni multi = multi_feeder ∨ aggregation;
   referans konsensüs dosyası varsa o, yoksa katı AND; eşik 0.6; Jev kodlanan koşusu "complete".
   Sonuç `a26_results.json` → `jev.coded.gate`'e yazılır; donmuş `jev --scale-out` bunu okur.
   Bilgi amaçlı: Jev κ'sı kodlayıcı-1'e karşı 263 cümlede.
Eksik kodlayıcı-2 satırları asla doldurulmaz.
Kullanım: GFP_RUN_DIR=oct_v42 python -m experiments.gfp_benchmark.coder_subset_analysis [konsensüs.csv]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from experiments.gfp_benchmark import scale_assertion_analysis as saa

HERE = Path(__file__).resolve().parent
SUBSET = HERE / "coder2_subset.json"
GATE_THRESHOLD = 0.6


def main(consensus: str | None = None) -> None:
    out_dir = saa.OUT
    c1 = out_dir.parent / "coded" / "scale_coded_coder1.csv"
    c2 = out_dir.parent / "coded" / "scale_coded_coder2.csv"
    sub = sorted(json.loads(SUBSET.read_text(encoding="utf-8"))["a26"]["80"])

    # 1) tahminler: donmuş analyze, kodlayıcı-1 tek etiket seti
    saa.analyze(str(c1), str(c1), str(c1))
    res_path = out_dir / "a26_results.json"
    frozen = json.loads(res_path.read_text(encoding="utf-8"))
    (out_dir / "a26_results_frozen_call.json").write_text(
        json.dumps(frozen, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    md_frozen = (out_dir / "a26_results.md").read_text(encoding="utf-8")

    key_ids = sorted(saa._read_coding(str(c1), []))           # tüm öğe kimlikleri (doğrulama aşağıda)
    r1 = saa._read_coding(str(c1), key_ids)
    r2 = saa._read_coding(str(c2), sub)
    extra = sorted(set(r2) - set(sub))
    if extra:
        sys.exit(f"kodlayıcı-2 dosyasında alt küme dışı {len(extra)} öğe var")

    # 2) güvenilirlik (örtüşme)
    rel = {}
    for v in saa.VARS:
        k = saa._kappa([r1[i][v] for i in sub], [r2[i][v] for i in sub])
        k["pabak"] = None if k["raw_agreement"] is None else round(2 * k["raw_agreement"] - 1, 4)
        rel[v] = k
    # 3) kodlayıcı-1 ↔ katı/gevşek farkları (örtüşme)
    diff = {v: {"coder1_Y_strict_N": sum(r1[i][v] == "Y" and r2[i][v] == "N" for i in sub),
                "coder1_N_lenient_Y": sum(r1[i][v] == "N" and r2[i][v] == "Y" for i in sub)}
            for v in saa.VARS}

    # 4) Jev κ-kapısı (örtüşme, donmuş tanım)
    jev_blk = frozen.get("jev", {})
    gate = {"status": "not run"}
    coded = out_dir / "a26_jev_coded.jsonl"
    if coded.exists():
        pred, meta = saa._jev_read(coded)
        multi = lambda d: d["scale_multi_feeder_YN"] or d["aggregation_YN"]
        if consensus:
            rc = saa._read_coding(consensus, sub)
            ref, ref_name = {i: rc[i] for i in sub}, "consensus"
        else:
            ref = {i: {v: "Y" if r1[i][v] == r2[i][v] == "Y" else "N" for v in saa.VARS} for i in sub}
            ref_name = "strict_AND"
        ks = [i for i in sub if i in pred]
        kap = saa._kappa(["Y" if multi(pred[i]) else "N" for i in ks],
                         ["Y" if multi({v: ref[i][v] == "Y" for v in saa.VARS}) else "N" for i in ks])
        gate = {"variable": "multi", "against": ref_name, "on": "A29 overlap (80)",
                "n": kap["n"], "kappa": kap["kappa"], "raw_agreement": kap["raw_agreement"],
                "status": meta["status"], "threshold": GATE_THRESHOLD,
                "passed": bool(kap["kappa"] is not None and kap["kappa"] >= GATE_THRESHOLD
                               and meta["status"] == "complete")}
        jev_blk.setdefault("coded", {})
        jev_blk["coded"]["coder1_all_info"] = jev_blk["coded"].pop("consensus", None)
        jev_blk["coded"]["gate_frozen_call_not_used"] = jev_blk["coded"].pop("gate", None)
        jev_blk["coded"]["gate"] = gate

    out = {"design": "A29: estimates from coder-1 on all sentences; reliability and Jev gate on the "
                     "seed-drawn 80-sentence overlap with coder-2",
           "n_items": frozen["n_items"], "n_overlap": len(sub),
           "reliability_overlap": rel, "coder1_vs_bounds_overlap": diff,
           "by_label_set": {"coder1": frozen["by_label_set"]["consensus"]},
           "jev": jev_blk}
    res_path.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (out_dir / "a26_results.md").write_text(md_frozen.replace("| consensus |", "| coder1 |"),
                                            encoding="utf-8")
    print(f"-> {res_path}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
