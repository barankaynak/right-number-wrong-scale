"""G4 ön-kayıtlı analiz — GFP vs legacy recall, exact McNemar, güç-katmanları.

Danışman v2.10 deliverable'ları: kategori-başı + Tier + genel recall; exact McNemar
(GFP-ref vs legacy-primary); kontrol-FP (3 legacy okuma); value_fab çarpan-katmanı;
kategori×GFP-ihlal-türü; scale_swap per-phrase kırılımı; atıl-enjeksiyon karakterizasyonu.

Kullanım: python -m experiments.gfp_benchmark.compute_g4 [results/raw_g4_final_*.jsonl]
"""
from __future__ import annotations
import glob
import json
import sys
from collections import Counter
from math import comb
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
CATS = ("scale_swap", "unit_swap", "value_fabrication", "small_int_fabrication")
TIER1 = ("scale_swap", "unit_swap")
TIER2 = ("value_fabrication", "small_int_fabrication")


def mcnemar_exact(pairs):
    """İki-yönlü exact McNemar; pairs = [(gfp_bool, legacy_bool), ...]."""
    b = sum(1 for g, l in pairs if g and not l)
    c = sum(1 for g, l in pairs if l and not g)
    n = b + c
    if n == 0:
        return {"b": b, "c": c, "n_discordant": 0, "p": 1.0}
    k = min(b, c)
    p = min(1.0, sum(comb(n, i) for i in range(k + 1)) / 2 ** n * 2)
    return {"b": b, "c": c, "n_discordant": n, "p": p}


def _recall(sub, key):
    d = sum(bool(r[key]) for r in sub if r.get(key) is not None)
    n = sum(1 for r in sub if r.get(key) is not None)
    return d, n


def analyze(path: Path) -> dict:
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    inj = [r for r in rows if r["kind"] == "injected"]
    ctl = [r for r in rows if r["kind"] == "control"]
    out = {"file": path.name, "n_injected": len(inj), "n_control": len(ctl)}

    # kategori-başı
    per_cat = {}
    for cat in CATS:
        sub = [r for r in inj if r["category"] == cat]
        if not sub:
            continue
        gfp_d, gfp_n = _recall(sub, "gfp_ref_detected")
        inr_d, inr_n = _recall(sub, "gfp_inrun_detected")
        lp_d, lp_n = _recall(sub, "legacy_primary_detected")
        pairs = [(r["gfp_ref_detected"], r["legacy_primary_detected"]) for r in sub]
        # GFP hangi ihlal-türüyle yakaladı
        vt = Counter()
        for r in sub:
            if r["gfp_ref_detected"]:
                for k in ("SCALE_VIOLATION", "UNIT_MISMATCH", "UNGROUNDED"):
                    if (r.get("gfp_ref_counts") or {}).get(k, 0):
                        vt[k] += 1
        per_cat[cat] = {
            "n": len(sub),
            "gfp_ref_recall": round(gfp_d / gfp_n, 3) if gfp_n else None,
            "gfp_inrun_recall": (f"{inr_d}/{inr_n}" if inr_n else "0/0"),
            "legacy_primary_recall": round(lp_d / lp_n, 3) if lp_n else None,
            "mcnemar_gfp_vs_legacy": mcnemar_exact(pairs),
            "gfp_violation_type": dict(vt),
            "inert_no_violation_created": sum(1 for r in sub if not r["gfp_ref_detected"]
                                              and not r["legacy_primary_detected"]),
        }
    out["per_category"] = per_cat

    # Tier + genel
    tiers = {}
    for name, cats in [("tier1_scale_unit", TIER1), ("tier2_value_smallint", TIER2),
                       ("overall", CATS)]:
        sub = [r for r in inj if r["category"] in cats]
        gfp_d, gfp_n = _recall(sub, "gfp_ref_detected")
        lp_d, lp_n = _recall(sub, "legacy_primary_detected")
        pairs = [(r["gfp_ref_detected"], r["legacy_primary_detected"]) for r in sub]
        tiers[name] = {
            "n": len(sub),
            "gfp_ref_recall": round(gfp_d / gfp_n, 3) if gfp_n else None,
            "legacy_primary_recall": round(lp_d / lp_n, 3) if lp_n else None,
            "mcnemar": mcnemar_exact(pairs),
        }
    out["tiers"] = tiers

    # kontrol FP (3 legacy okuma + GFP)
    def fp(key):
        d, n = _recall(ctl, key)
        return {"fp": d, "n": n, "rate": round(d / n, 3) if n else None}
    out["control_fp"] = {
        "gfp_ref": fp("gfp_ref_detected"),
        "legacy_primary_violations": fp("legacy_primary_detected"),
        "legacy_s1_warnings": fp("legacy_s1_warn_detected"),
        "legacy_s2_ceiling": fp("legacy_s2_ceiling_detected"),
    }

    # value_fab çarpan-katmanı
    vf = [r for r in inj if r["category"] == "value_fabrication" and r.get("value_fab_multiplier")]
    strata = {}
    for lo, hi, lbl in [(0, 2, "lt_2x"), (2, 99, "gte_2x")]:
        s = [r for r in vf if lo <= r["value_fab_multiplier"] < hi]
        if s:
            gfp_d, gfp_n = _recall(s, "gfp_ref_detected")
            lp_d, lp_n = _recall(s, "legacy_primary_detected")
            strata[lbl] = {"n": len(s), "gfp_ref_recall": round(gfp_d / gfp_n, 3),
                           "legacy_primary_recall": round(lp_d / lp_n, 3)}
    out["value_fab_multiplier_strata"] = strata

    # scale_swap atıl-karakterizasyonu (kaç enjeksiyon SCALE_VIOLATION yarattı)
    ss = [r for r in inj if r["category"] == "scale_swap"]
    out["scale_swap_created_violation"] = {
        "n": len(ss),
        "created_scale_violation": sum(1 for r in ss if (r.get("gfp_ref_counts") or {}).get("SCALE_VIOLATION", 0)),
        "inert_no_gfp_violation": sum(1 for r in ss if not r["gfp_ref_detected"]),
    }
    return out


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if args:
        path = Path(args[0])
        if not path.is_absolute():
            path = HERE.parent / path if (HERE.parent / path).exists() else RESULTS / Path(args[0]).name
    else:
        hits = sorted(glob.glob(str(RESULTS / "raw_g4_final_seed*_*.jsonl")))
        path = Path(hits[-1])
    print(json.dumps(analyze(path), ensure_ascii=False, indent=2))
