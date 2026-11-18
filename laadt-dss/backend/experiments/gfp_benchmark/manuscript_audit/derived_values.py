#!/usr/bin/env python3
"""Derived values printed in the manuscript but not stored as such in one output file.

Each entry is recomputed here from released analysis outputs only, and written to
derived_values.json, which audit_numerals.py then uses as an additional source. Every
entry states its formula and its inputs. Nothing here re-runs an analysis; it only
sums, subtracts, averages or forms a Wilson interval from stored counts.

Standard library only. Usage:  python -I derived_values.py
"""
from __future__ import annotations

import ast
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
RES = HERE.parent / "results"


def wilson_pct(k: int, n: int, z: float = 1.959963984540054):
    """Wilson score interval for k/n, in percent (two-sided 95%)."""
    if n == 0:
        return None
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [round(100 * (centre - half), 4), round(100 * (centre + half), 4)]


def jev_table():
    """Table tab:jev -- Jev columns pooled over the tr, en and mistral stored-text sets."""
    s = json.loads((RES / "a25_jev_summary.json").read_text(encoding="utf-8"))["by_threshold"]["0.8"]
    out = {}
    for cat in ("scale_swap", "unit_swap", "value_fabrication", "small_int_fabrication"):
        cells = [s["recall"][f"{lang}|{cat}"] for lang in ("tr", "en", "mistral")]
        n = sum(c["raw"]["n"] for c in cells)
        row = {"n": n}
        for fmt in ("raw", "annotated"):
            k = sum(c[fmt]["detected"] for c in cells)
            row[fmt] = {"detected": k, "wilson_pct": wilson_pct(k, n)}
        out[cat] = row
    fp = {}
    for fmt in ("raw", "annotated"):
        cells = [s["original_sentence_fp"][f"{lang}|{fmt}"] for lang in ("tr", "en", "mistral")]
        n = sum(c["n"] for c in cells)
        k = sum(c["flagged"] for c in cells)
        ctrl = [s["control_fp"][f"{lang}|{fmt}"] for lang in ("tr", "en", "mistral")]
        fp[fmt] = {"original_n": n, "original_flagged": k, "wilson_pct": wilson_pct(k, n),
                   "control_n": sum(c["n"] for c in ctrl),
                   "control_flagged": sum(c["flagged"] for c in ctrl)}
    out["unmutated_and_controls"] = fp
    return {"formula": "sum over tr+en+mistral of a25_jev_summary.json by_threshold[0.8] cells; "
                       "Wilson 95% on the pooled count",
            "inputs": ["results/a25_jev_summary.json"], "values": out}


# the stored-text G4 sets used by the verifier (a23_legacy_decomposition.G4_SETS);
# the tr file is the seeded regeneration that stores the mutated texts (97 injections)
G4_RAW = {"tr": "raw_g4_final_seed42_20260710T074242Z.jsonl",
          "en": "raw_g4_final_en_seed42_20260710T190205Z.jsonl",
          "mistral": "raw_g4_final_mistral-small3.2-24b_seed42_20260710T225730Z.jsonl"}


def jev_gfp_reference():
    """Table tab:jev, GFP (reference) column: gfp_ref_detected of the stored-text G4 runs for
    the verifier's items. Items are aligned to G4 rows by (qid, category) in order, and the
    alignment is confirmed by the stored mutated text."""
    items = json.loads((RES / "a25_evidence_items.json").read_text(encoding="utf-8"))["items"]
    per_set, pooled = {}, {}
    for s, fname in G4_RAW.items():
        rows = [json.loads(ln) for ln in (RES / fname).read_text(encoding="utf-8").splitlines() if ln.strip()]
        rows = [r for r in rows if r.get("kind") == "injected"]
        its = sorted((i for i in items if i["set"] == s and i["kind"] == "injected"),
                     key=lambda i: int(i["id"].split("-")[1]))
        j, confirmed, cnt = 0, 0, {}
        for it in its:
            while not (rows[j]["qid"] == it["qid"] and rows[j]["category"] == it["category"]):
                j += 1
            row = rows[j]
            j += 1
            mt = row.get("mutated")
            if mt is not None:
                mt = mt if isinstance(mt, str) else json.dumps(mt, ensure_ascii=False)
                confirmed += it["mutated_sentence"][:30] in mt
            c = cnt.setdefault(it["category"], [0, 0])
            c[0] += bool(row["gfp_ref_detected"])
            c[1] += 1
        per_set[s] = {"counts": cnt, "alignment_confirmed_by_text": f"{confirmed}/{len(its)}"}
        for cat, (k, n) in cnt.items():
            p = pooled.setdefault(cat, [0, 0])
            p[0] += k
            p[1] += n
    return {"formula": "gfp_ref_detected summed over aligned stored-text items; Wilson 95%",
            "inputs": ["results/a25_evidence_items.json"] + [f"results/{f}" for f in G4_RAW.values()],
            "values": {"per_set": per_set,
                       "pooled": {c: {"detected": k, "n": n, "wilson_pct": wilson_pct(k, n)}
                                  for c, (k, n) in pooled.items()}}}


def g4_pooled_recall():
    """Pooled GFP detections over the four G4 categories (Turkish primary set). The paper
    treats this pooled figure as descriptive only; it appears in the graphical abstract."""
    pc = json.loads((RES / "g4_summary.json").read_text(encoding="utf-8"))["per_category"]
    det = {c: sum(v["gfp_violation_type"].values()) for c, v in pc.items()}
    n = {c: v["n"] for c, v in pc.items()}
    return {"formula": "sum over categories of g4_summary.json per_category[c].gfp_violation_type "
                       "counts, and of per_category[c].n",
            "inputs": ["results/g4_summary.json"],
            "values": {"per_category_detected": det, "pooled": {"detected": sum(det.values()),
                                                               "n": sum(n.values())}}}


def _read_json_out(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _read_tol_out(path: Path):
    """tol_tax*.out lines: '<band> <python dict>'."""
    rows = {}
    for ln in path.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        band, rest = ln.split(" ", 1)
        rows[band] = ast.literal_eval(rest)
    return rows


def taxonomy_model_b():
    """Model B = (Models A+B run) minus (Model A run), Turkish taxonomy and its sweep."""
    a = _read_json_out(RES / "oct_v42/analysis/taxonomy.out")
    ab = _read_json_out(RES / "oct_v42/analysis/taxonomy_AB.out")
    keys = ("n_blocked_responses", "n_blocked_analysed_with_inrun_graph", "n_flags")
    b = {k: ab[k] - a[k] for k in keys}
    b["categories"] = {c: ab["categories"][c] - a["categories"][c] for c in ab["categories"]}
    b["category_pct"] = {c: round(100 * v / b["n_flags"], 4) for c, v in b["categories"].items()}
    ta = _read_tol_out(RES / "oct_v42/analysis/tol_tax.out")
    tab = _read_tol_out(RES / "oct_v42/analysis/tol_tax_AB.out")
    sweep = {}
    for band in tab:
        n = tab[band]["n_flags"] - ta[band]["n_flags"]
        cats = {c: tab[band]["categories"][c] - ta[band]["categories"][c] for c in tab[band]["categories"]}
        sweep[band] = {"n_flags": n, "categories": cats,
                       "category_pct": {c: round(100 * v / n, 4) for c, v in cats.items()}}
    return {"formula": "taxonomy_AB.out minus taxonomy.out (Model A); same for tol_tax_AB.out "
                       "minus tol_tax.out per tolerance band",
            "inputs": ["results/oct_v42/analysis/taxonomy.out", "results/oct_v42/analysis/taxonomy_AB.out",
                       "results/oct_v42/analysis/tol_tax.out", "results/oct_v42/analysis/tol_tax_AB.out"],
            "values": {"model_b": b, "model_b_sweep": sweep}}


def multiturn():
    """G1-MT arm means over the 20 scorable questions, the usability cost, and counts."""
    m = json.loads((RES / "oct_v42_mt/mt_results.json").read_text(encoding="utf-8"))
    means = {}
    for key, per_q in m["TU_question_means"].items():
        vals = list(per_q.values())
        means[key] = round(sum(vals) / len(vals), 6)
    cost = {t: round(means[f"grounded_noguard|{t}"] - means[f"grounded_guard|{t}"], 6)
            for t in ("turn1", "turn2")}
    blk = m["secondary_b_guard_turn2_blocked"]
    guarded_turn2 = blk["turn2_tool_called"]["n"] + blk["turn2_no_tool"]["n"]
    return {"formula": "mean over questions of TU_question_means[arm|turn]; cost = noguard - guard; "
                       "guarded second turns = tool-called n + no-tool n",
            "inputs": ["results/oct_v42_mt/mt_results.json"],
            "values": {"arm_turn_means": means, "usability_cost": cost,
                       "guarded_second_turns": guarded_turn2,
                       "blocked_with_tool_pct": round(100 * blk["turn2_tool_called"]["blocked"]
                                                      / blk["turn2_tool_called"]["n"], 4)}}


def _sens_rows(fname):
    return json.loads((RES / "sens_v225" / fname).read_text(encoding="utf-8"))


def matcher_sensitivity():
    """Post-outcome matcher sensitivity (prereg-v3.8): shares and sums of the stored S1/S2/S4 counts.

    Block denominators are S1's (records flagged `fallback` excluded, as in the paper); S4's raw
    `blocked` differs only for Model C, G1-MT turn 2 (34 vs 33), and the extra record passes no rule.
    """
    s1, s2 = _sens_rows("s1_p3_split.json"), _sens_rows("s2_incidence.json")
    s4 = _sens_rows("s4_block_attribution.json")
    per, empty, tools = {}, {}, {}
    for k, v in s4["per_unit"].items():
        blk = s1[k]["blocked"]
        e = s1[k].get("records_but_empty_summary", 0)
        per[k] = {v_: {"n": v[f"blocked_draft_passes_{v_}"], "of": blk,
                       "pct": round(100 * v[f"blocked_draft_passes_{v_}"] / blk, 4)}
                  for v_ in ("sign", "decimal", "both")}
        empty[k] = {"n": e, "of_guarded": v["evaluated"], "pct": round(100 * e / v["evaluated"], 4)}

    def pool(run, unit, var="both"):
        ks = [k for k in per if k.startswith(run + "|") and k.endswith("|" + unit)]
        n, of = sum(per[k][var]["n"] for k in ks), sum(per[k][var]["of"] for k in ks)
        return {"n": n, "of": of, "pct": round(100 * n / of, 4)}

    g1 = [k for k in s1 if k.startswith("oct_v42|") and k.endswith("|t1")]
    for k in g1:
        for a, b in s1[k].items():
            if a.startswith("records_but_empty_summary|last="):
                t = a.split("last=")[1].split("|")[0]
                tools[t] = tools.get(t, 0) + b
                if "failed=True" in a:
                    tools[t + "|failed"] = tools.get(t + "|failed", 0) + b
    ip = json.loads((RES / "oct_v42/intervention_paths.json").read_text(encoding="utf-8"))
    p3 = {}
    for k in g1:
        key = ("en|" if "_en_" in k else "tr|") + {"gemma4-e4b": "gemma4:e4b", "qwen3.8-27b": "qwen3.8:27b",
               "mistral-small3.2-24b": "mistral-small3.2:24b", "muse-glimmer-30b": "muse-glimmer:30b"}[
            k.split("raw_g1_")[1].split("_")[0]]
        p3[k] = round(100 * empty[k]["n"] / ip[key]["paths"]["P3"]["n"], 4)
    mt_b = [k for k in s1 if k.startswith("oct_v42_mt|") and "qwen" in k and k.endswith("|t2")]
    mtb = {"empty": sum(s1[k].get("records_but_empty_summary", 0) for k in mt_b),
           "blocked": sum(s1[k]["blocked"] for k in mt_b),
           "no_call": sum(s1[k].get("records_but_empty_summary|no_call_this_unit", 0) for k in mt_b),
           "failed_call": sum(b for k in mt_b for a, b in s1[k].items() if "failed=True" in a)}
    inc = {}
    for arm in ("grounded_guard", "grounded_noguard", "ungrounded"):
        vals = [100 * r["decimal"]["units_counts_changed"] / r["_n"]["units"]
                for k, r in s2.items() if k.startswith("oct_v42|") and f"|{arm}|delivered_ref" in k]
        runs = {}
        for run in ("oct_v42", "oct_v42_mt", "oct_v42_evren"):
            rs = [r for k, r in s2.items() if k.startswith(run + "|") and f"|{arm}|delivered_ref" in k]
            runs[run] = round(100 * sum(r["decimal"]["units_counts_changed"] for r in rs)
                              / sum(r["_n"]["units"] for r in rs), 4)
        inc[arm] = {"g1_condition_min_pct": round(min(vals), 4), "g1_condition_max_pct": round(max(vals), 4),
                    "pooled_per_run_pct": runs,
                    "pooled_per_run_min_pct": min(runs.values()), "pooled_per_run_max_pct": max(runs.values())}
    # frozen vs both re-analyses: tool lift and H_G1b (Holm p, bootstrap mean), taxonomy totals
    an = RES / "sens_v225" / "analysis"
    reanal = {}
    for v in ("frozen", "decimal", "both"):
        for f in sorted(an.glob(f"{v}/gfs_*.out")):
            if "pooled" in f.name:
                continue
            t = f.read_text(encoding="utf-8")
            d = json.loads(t[t.find("{"):t.rfind("}") + 1])["G1_reference_gfs"]
            reanal.setdefault(f.name[4:-4], {})[v] = {
                "tool_lift_holm_p": d["H_G1a_aux"]["wilcoxon"]["p_holm"],
                "g1b_mean_diff": round(d["H_G1b"]["bootstrap"]["mean_diff"], 6)}
    for c in reanal.values():
        if "both" in c and "frozen" in c:
            c["g1b_change_both"] = round(c["both"]["g1b_mean_diff"] - c["frozen"]["g1b_mean_diff"], 6)
    a30 = {}
    for v in ("frozen", "both"):
        g = json.loads((an / v / "oct_v42_evren/a30_gfs.json").read_text(encoding="utf-8"))
        a30[v] = round(g["deepseek-v4.1-flash"]["G1_reference_gfs"]["H_G1b"]["bootstrap"]["mean_diff"], 6)
    reanal["deepseek"] = {"g1b_change_both": round(a30["both"] - a30["frozen"], 6)}
    ch = [c["g1b_change_both"] for c in reanal.values() if "g1b_change_both" in c]
    tax = {}
    for v in ("frozen", "decimal", "both"):
        t = (an / v / "taxonomy.out").read_text(encoding="utf-8")
        j = json.loads(t[t.find("{"):t.rfind("}") + 1])
        tax[v] = {"n_flags": j["n_flags"], "small_int_context": j["categories"]["small_int_context"]}
    mt_t2 = {k.split("|")[1]: per[k]["both"] for k in per if k.startswith("oct_v42_mt|") and k.endswith("|t2")}
    fail = {}
    for x in s4["summaries_failing_own_check"]:
        key = x["file"].split("|")[0] + "|" + x["unit"]
        fail[key] = fail.get(key, 0) + 1
    return {"formula": "S4 blocked_draft_passes_<rule> / S1 blocked (per unit and pooled); S1 empty-summary / "
                       "S4 evaluated and / P3 n; S1 last-tool sums; S2 decimal units_counts_changed / units",
            "inputs": ["results/sens_v225/s1_p3_split.json", "results/sens_v225/s2_incidence.json",
                       "results/sens_v225/s4_block_attribution.json", "results/oct_v42/intervention_paths.json"],
            "values": {"per_unit": per, "summary_empty": empty, "summary_empty_pct_of_p3": p3,
                       "g1_empty_by_last_tool": tools,
                       "g1_empty_total": sum(empty[k]["n"] for k in g1),
                       "pooled_g1_both": pool("oct_v42", "t1"), "pooled_mt_t2_both": pool("oct_v42_mt", "t2"),
                       "model_b_mt_turn2": mtb, "decimal_units_changed": inc,
                       "reanalysis": reanal,
                       "g1b_change_both_range": [round(min(ch), 4), round(max(ch), 4)],
                       "taxonomy_pooled": tax,
                       "mt_turn2_both_pct": {"min": round(min(x["pct"] for x in mt_t2.values()), 4),
                                             "max": round(max(x["pct"] for x in mt_t2.values()), 4)},
                       "summaries_failing_own_check": fail}}


def main():
    out = {"note": "Recomputed from released outputs by derived_values.py; see each formula.",
           "matcher_sensitivity": matcher_sensitivity(),
           "g4_pooled_recall": g4_pooled_recall(),
           "jev_table": jev_table(), "jev_gfp_reference": jev_gfp_reference(),
           "taxonomy_model_b": taxonomy_model_b(),
           "multiturn": multiturn()}
    (HERE / "derived_values.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1)[:3000])


if __name__ == "__main__":
    main()
