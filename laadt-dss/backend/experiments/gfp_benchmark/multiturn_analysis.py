"""A28-2/A28-3 (A29-4 ile) — G1-MT analizi ve TU vekil doğrulaması [hash'i koşu-öncesi Beyan'da].

TU (izlenebilir kullanılabilir cevap): tur kaydındaki guard raporunda (`provenance.claims`, teslim
metni) verdict'i GROUNDED olan, `matched_key`'i `input:` ile başlamayan ve normalize anahtarı
(`[n]`→`[]`) sorunun `numeric_focus` etiketlerinden birinin `answer_keys.json` regex'ine
`re.fullmatch` ile uyan ≥1 iddia varsa 1, yoksa 0.

  validate — A22-2'nin 86 yanıtı G1 kayıtlarına eşlenir (`audit_sample.py`'nin seed-42 seçimi aynen
             yeniden üretilir; soru metniyle `audit_items.jsonl`'a karşı assert'li). TU ile her
             kodlayıcının `usable_answer_YN`'i: κ, ham uyum, PABAK. Ölçüt (A28-3/A29-4): her iki
             kodlayıcı için κ ≥ 0.70 ya da ham uyum ≥ 0.85.
  analyze  — H_MT1, H_MT2 (soru düzeyi eşli Wilcoxon, Holm), bootstrap GA, clear-17 duyarlılığı,
             ikincil (a)–(e). Donmuş `compute_gfs` yardımcıları kullanılır.
Kullanım: GFP_RUN_DIR=oct_v42 [GFP_MT_DIR=oct_v42_mt] python -m experiments.gfp_benchmark.multiturn_analysis validate|analyze
"""
from __future__ import annotations

import csv
import json
import os
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

from experiments.gfp_benchmark.compute_gfs import bootstrap_diff_ci, gfs_from_counts, holm, wilcoxon_pair
from experiments.gfp_benchmark.scale_assertion_analysis import _kappa

HERE = Path(__file__).resolve().parent
G1_RUN = HERE / "results" / os.environ.get("GFP_RUN_DIR", "oct_v42")
MT_RUN = HERE / "results" / os.environ.get("GFP_MT_DIR", "oct_v42_mt")
TURN2 = json.loads((HERE / "multiturn_turn2.json").read_text(encoding="utf-8"))["questions"]
AK = {k: [re.compile(p) for p in v] for k, v in
      json.loads((HERE / "answer_keys.json").read_text(encoding="utf-8"))["labels"].items()}
SUBSET = json.loads((HERE / "coder2_subset.json").read_text(encoding="utf-8"))
ARMS = ("grounded_guard", "grounded_noguard", "ungrounded")
TRAPS = ("res-11", "res-12", "com-10", "sta-07", "sta-10")
KAPPA_MIN, RAW_MIN = 0.70, 0.85


def tu(provenance: dict | None, numeric_focus: list[str]) -> int:
    pats = [p for f in numeric_focus for p in AK[f]]
    for c in (provenance or {}).get("claims") or []:
        k = c.get("matched_key")
        if c.get("verdict") != "GROUNDED" or not k or k.startswith("input:"):
            continue
        if any(p.fullmatch(re.sub(r"\[\d+\]", "[]", k)) for p in pats):
            return 1
    return 0


# ── validate ─────────────────────────────────────────────────────────────────

def _audit_records() -> dict:
    """audit_sample.main()'in seçimini aynen yeniden üretir: item → G1 kaydı."""
    from experiments.gfp_benchmark.audit_sample import SEED, TARGETS, _allocate
    from experiments.gfp_benchmark.intervention_paths import classify
    from experiments.gfp_benchmark.rescore_crosslingual import FILE_GLOBS, _latest
    rng = random.Random(SEED)
    strata = defaultdict(list)
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
    recs = {f"A{i:03d}": r for i, (_, _, r) in enumerate(chosen, 1)}
    lines = (G1_RUN / "audit" / "audit_items.jsonl").read_text(encoding="utf-8").splitlines()
    items = {d["item"]: d for d in map(json.loads, filter(str.strip, lines))}
    for item, r in recs.items():
        q = r["question"]["question_en"] if r.get("lang") == "en" else r["question"]["question_tr"]
        assert items[item]["question"] == q, f"{item}: seçim yeniden üretilemedi"
    assert set(recs) == set(items)
    return recs


def _usable(path: Path) -> dict:
    out = {}
    for r in csv.DictReader(path.open(encoding="utf-8-sig", newline="")):
        out.setdefault(r["item"].strip(), r["usable_answer_YN"].strip().upper())
    return out


def validate() -> dict:
    recs = _audit_records()
    proxy = {i: "Y" if tu(r.get("provenance"), r["question"]["numeric_focus"]) else "N"
             for i, r in recs.items()}
    res = {"n_items": len(proxy), "proxy_Y": sum(v == "Y" for v in proxy.values())}
    passed = True
    for name, f, ids in (("coder1", "audit_coded_coder1.csv", sorted(proxy)),
                         ("coder2", "audit_coded_coder2.csv", sorted(SUBSET["a22"]["30"]))):
        h = _usable(G1_RUN / "coded" / f)
        k = _kappa([proxy[i] for i in ids], [h[i] for i in ids])
        k["pabak"] = None if k["raw_agreement"] is None else round(2 * k["raw_agreement"] - 1, 4)
        k["cells"] = {f"proxy{a}_human{b}": sum(proxy[i] == a and h[i] == b for i in ids)
                      for a in "YN" for b in "YN"}
        k["criterion_met"] = bool((k["kappa"] is not None and k["kappa"] >= KAPPA_MIN)
                                  or (k["raw_agreement"] is not None and k["raw_agreement"] >= RAW_MIN))
        passed &= k["criterion_met"]
        res[name] = k
    res["proxy_valid"] = passed
    res["rule"] = f"each coder: kappa >= {KAPPA_MIN} or raw agreement >= {RAW_MIN} (A28-3, A29-4)"
    out = G1_RUN / "audit" / "tu_proxy_validation.json"
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"-> {out}")
    return res


# ── analyze ──────────────────────────────────────────────────────────────────

def _rows() -> list[dict]:
    rows = []
    for f in sorted(MT_RUN.glob("raw_mt_*.jsonl")):
        rows += [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
    return rows


def _qmean(convs: list[dict], fn) -> dict:
    by_q = defaultdict(list)
    for c in convs:
        v = fn(c)
        if v is not None:
            by_q[c["question"]["id"]].append(v)
    return {q: float(np.mean(v)) for q, v in by_q.items()}


def _tests(cells: dict, qids: list[str]) -> dict:
    g1, g2 = cells[("grounded_guard", 0)], cells[("grounded_guard", 1)]
    n1, n2 = cells[("grounded_noguard", 0)], cells[("grounded_noguard", 1)]
    q1 = [q for q in qids if q in g1 and q in g2]
    q2 = [q for q in qids if all(q in d for d in (g1, g2, n1, n2))]
    a1, b1 = np.array([g2[q] for q in q1]), np.array([g1[q] for q in q1])
    a2 = np.array([n2[q] - g2[q] for q in q2])
    b2 = np.array([n1[q] - g1[q] for q in q2])
    t = {"H_MT1": {"n_questions": len(q1), **wilcoxon_pair(a1, b1), **bootstrap_diff_ci(a1, b1),
                   "label": "guard arm TU, turn 2 minus turn 1"},
         "H_MT2": {"n_questions": len(q2), **wilcoxon_pair(a2, b2), **bootstrap_diff_ci(a2, b2),
                   "label": "usability cost C = TU(noguard) - TU(guard), turn 2 minus turn 1"}}
    adj = holm({k: v["p"] for k, v in t.items()})
    for k in t:
        t[k]["p_holm"] = adj[k]
    return t


def analyze() -> dict:
    rows = _rows()
    convs = [r for r in rows if not (r.get("fallback") or r.get("error"))]
    answerable = sorted(q for q, v in TURN2.items() if v["answerable"])
    clear = sorted(q for q in answerable if TURN2[q]["subset"] == "clear")
    focus = lambda c: c["question"]["numeric_focus"]
    cells = {}
    for arm in ARMS:
        cs = [c for c in convs if c["config"] == arm and c["question"]["id"] in answerable]
        for t in (0, 1):
            cells[(arm, t)] = _qmean(cs, lambda c, t=t: tu(c["turns"][t]["provenance"], focus(c)))
    res = {"n_rows": len(rows), "n_excluded": len(rows) - len(convs),
           "by_condition_n": {f"{l}|{m}": sum(1 for c in convs if (c["lang"], c["model"]) == (l, m))
                              for l, m in sorted({(c["lang"], c["model"]) for c in rows})},
           "questions": {"answerable": answerable, "clear": clear},
           "TU_question_means": {f"{a}|turn{t + 1}": v for (a, t), v in cells.items()},
           "primary": _tests(cells, answerable), "sensitivity_clear17": _tests(cells, clear)}
    # (a) tur-2 referans-GFS
    ref = {arm: _qmean([c for c in convs if c["config"] == arm],
                       lambda c: gfs_from_counts((c["turns"][1].get("reference_check") or {}).get("counts")))
           for arm in ARMS}
    qq = [q for q in ref["grounded_guard"] if q in ref["grounded_noguard"]]
    res["secondary_a_turn2_reference_gfs"] = {
        "arm_mean": {a: (float(np.mean(list(v.values()))) if v else None) for a, v in ref.items()},
        "guard_vs_noguard": {"n_questions": len(qq),
                             **wilcoxon_pair(np.array([ref["grounded_guard"][q] for q in qq]),
                                             np.array([ref["grounded_noguard"][q] for q in qq]))}}
    # (b) guard kolu tur-2 bloklama, tur-2 araç çağrısına göre
    g = [c for c in convs if c["config"] == "grounded_guard"]
    blk = defaultdict(lambda: [0, 0])
    for c in g:
        p = c["turns"][1].get("provenance") or {}
        key = "turn2_tool_called" if p.get("tool_trace") else "turn2_no_tool"
        blk[key][0] += bool(p.get("blocked"))
        blk[key][1] += 1
    res["secondary_b_guard_turn2_blocked"] = {k: {"blocked": b, "n": n} for k, (b, n) in blk.items()}
    # (c) koşul başına TU
    tab = {}
    for (l, m) in sorted({(c["lang"], c["model"]) for c in convs}):
        for arm in ARMS:
            cs = [c for c in convs if (c["lang"], c["model"], c["config"]) == (l, m, arm)
                  and c["question"]["id"] in answerable]
            tab[f"{l}|{m}|{arm}"] = [round(float(np.mean([tu(c["turns"][t]["provenance"], focus(c))
                                                           for c in cs])), 4) if cs else None
                                     for t in (0, 1)]
    res["secondary_c_TU_by_condition_turn1_turn2"] = tab
    # (d) tur-1 araç çağırma oranı
    res["secondary_d_turn1_tool_rate"] = {
        arm: round(float(np.mean([bool((c["turns"][0].get("provenance") or {}).get("tool_trace"))
                                  for c in convs if c["config"] == arm])), 4)
        for arm in ARMS if any(c["config"] == arm for c in convs)}
    # (e) tuzak soruları tur-2 SCALE_VIOLATION
    res["secondary_e_traps_turn2_scale_violations"] = {
        arm: sum(((c["turns"][1].get("provenance") or {}).get("counts") or {}).get("SCALE_VIOLATION", 0)
                 for c in convs if c["config"] == arm and c["question"]["id"] in TRAPS)
        for arm in ARMS}
    val = G1_RUN / "audit" / "tu_proxy_validation.json"
    res["proxy_validation"] = json.loads(val.read_text(encoding="utf-8")) if val.exists() else None
    out = MT_RUN / "mt_results.json"
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    print(f"-> {out}")
    return res


if __name__ == "__main__":
    {"validate": validate, "analyze": analyze}[sys.argv[1]]()
