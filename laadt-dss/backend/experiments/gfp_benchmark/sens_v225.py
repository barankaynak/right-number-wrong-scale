"""v2.25 matcher sensitivity [POST-OUTCOME, exploratory; SCIENTIFIC_REVIEW v2.25, PREREGISTRATION Beyan 2026-11-14].

The frozen guard (`app/llm/provenance_guard.py`, sha a050b46a…) has two matcher defects found after the
outcomes were known:
- (1) `_NUM_RE` captures no sign;
- (2) it splits a numeral with 1-3 integer digits and >=4 decimals ("1.1015" -> "1.101" + "5").

This script re-scores the STORED texts under four matcher variants:
- frozen;
- sign: the shared `claim_sign` rule;
- decimal;
- both.

It makes no LLM calls. The guard's live decisions (blocked, retried, delivered reply) are never changed; only
scoring changes. The primary results remain those of the frozen matcher.

Variants:
- frozen:  the frozen ProvenanceGraph.check_response and _NUM_RE.
- sign:    check_response from `sens_v225_v5.py`, a byte-identical copy of the platform's provenance_guard_v5.py
           (sha a477e0eb…, platform/ems 9c5de68). A claim takes its sign from `claim_sign`; a signed claim matches
           only a same-sign record; an unsigned claim never matches a negative record.
- decimal: `_NUM_RE` gets one extra alternative, tried first:
               \\d{1,3}[.,]\\d{4,}(?![.,]?\\d)
           A token of 1-3 integer digits, one separator and >=4 fractional digits, not followed by another
           separator+digit, is read as ONE number. `_candidate_values` is unchanged. A numeral with a thousands
           group AND >=4 decimals ("1,234.5678") is outside the rule and keeps the frozen split.
- both:    sign and decimal together.
The variants are installed by patching the frozen module in memory (`variant()`). No file under app/ is changed.

Stages (order binding; SCIENTIFIC_REVIEW v2.25):
- S0 gate: the frozen matcher must reproduce the stored counts EXACTLY, per stage:
    - reference_check.counts: delivered text vs the reference graph, built by the run-time builder
      (run_benchmark._reference_graph);
    - provenance.counts: delivered text vs the in-run graph;
    - provenance.pre_intervention.counts: first draft vs the in-run graph.
  The in-run graph is rebuilt from tool_trace via the deterministic simulator, adding every call as the live
  orchestrator does. In MT, turn k starts from the session's stored, capped records.
  A trace failing the reference gate is dropped from ALL variant copies, so variant deltas are read against the
  frozen COPY, not against printed numbers. A unit failing an in-run gate keeps its stored in-run fields in all
  variants, is flagged, and is left out of S2 (in-run), S4 and S5. All failures are counted.
- S1: P3 split from stored strings only, per guard-arm blocked unit:
    - empty graph;
    - records present but the summary is empty, split by the unit's last call (tool name and failed flag), or
      "no call this unit" (MT turn 2: records from turn 1, nothing called now);
    - summary with numbers.
- S2: defect incidence per run x file x arm x stage:
    - minus-prefixed and long-decimal numerals in the scored texts;
    - per variant, summed verdict counts and units whose counts / pass status differ from frozen;
    - for `sign` (tokenisation unchanged, claims align 1:1), a paired frozen->sign verdict cross-tab.
- S3: the frozen analysis scripts run unchanged on variant copies under the patched matcher (`analyze`).
- S4: block attribution, a lower bound. Guard-arm retried units whose first draft passes under the variant;
  delivered summaries failing their own check, listed one by one.
- S5: fail-open. Minus-prefixed claims GROUNDED by the frozen matcher in delivered guard-arm text, with the sign
  of the matched in-run record. The position comes from a frozen-regex re-scan (one claim per match).
- S6: A22 audit numerals that are signed or >=4-decimal, crossed with matcher verdict and coder-1 labels. The flag
  taxonomy is re-run under the variants in `analyze`.
- S7: G4 corpus (raw_g4_final*): signed and >=4-decimal numerals in source/mutated texts.

Usage (inside the backend container, cwd /app):
    python -m experiments.gfp_benchmark.sens_v225 check                          # hashes + self-tests + fixture
    python -m experiments.gfp_benchmark.sens_v225 rescore [--runs oct_v42,...]   # S0, S2, S4, S5 + copies
    python -m experiments.gfp_benchmark.sens_v225 strings                        # S1, S6, S7 (no simulator)
    python -m experiments.gfp_benchmark.sens_v225 analyze                        # S3 (+ taxonomy for S6)
    python -m experiments.gfp_benchmark.sens_v225 exec <variant> <module> [args] # internal: patched runpy
Environment:
- SENS_OUT: output dir under results/ (default sens_v225);
- SENS_VARIANTS: comma list (default all four);
- SENS_DRYRUN=1: write only gate.json from rescore; S2/S4/S5 are computed but not written.
Outputs: results/<SENS_OUT>/{gate,s1,s2,s4,s5,s6,s7}.json and analysis/<variant>/*.out.
Work copies: results/<SENS_OUT>/_work/<variant>/<run>/ hold rescored traces plus an allowlist of support files the
S3 jobs read. They never hold coder files or the A22 blinding key, are reproducible, and may be deleted afterwards.
"""
from __future__ import annotations

import contextlib
import copy
import glob
import hashlib
import json
import os
import re
import runpy
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
RES = HERE / "results"
OUT = RES / os.environ.get("SENS_OUT", "sens_v225")
WORK = OUT / "_work"
APP = HERE.parent.parent / "app" / "llm"
DRYRUN = os.environ.get("SENS_DRYRUN") == "1"

GUARD_SHA = "a050b46ab5d8fa392215a1df47162c311daae95118d2bfa311d31e84a729f7c2"
ORCH_SHA = "283ccfe725bf45d34498cfa0acd2eeab76c0e553bcd3bc2e422f1a388296b94e"
V5_SHA = "a477e0eb8d6e5778390eb8a12acf8f818d136d2860bac23d007983b9f69867b1"
ALL_VARIANTS = ("frozen", "sign", "decimal", "both")
VARIANTS = tuple(v for v in os.environ.get("SENS_VARIANTS", ",".join(ALL_VARIANTS)).split(",") if v)
assert VARIANTS and VARIANTS[0] == "frozen" and set(VARIANTS) <= set(ALL_VARIANTS), VARIANTS
RUNS = {  # run dir -> raw trace globs (exactly the files the frozen analyses read; aborted_* never match)
    "oct_v42": ["raw_g1_*.jsonl"],
    "oct_v42_mt": ["raw_mt_*.jsonl"],
    "oct_v42_evren": ["raw_g1_*.jsonl", "raw_mt_*.jsonl"],
}
SUPPORT = {  # run dir -> non-trace files the S3 jobs read (allowlist; nothing else is copied)
    "oct_v42": ["audit/tu_proxy_validation.json"],
    "oct_v42_mt": [],
    "oct_v42_evren": ["a30_calls.jsonl", "determinism_check_*.jsonl"],
}
EMPTY_SUMMARY = ("özetlenebilir sayısal alan bulunamadı", "no summarizable numeric field found")
EMPTY_GRAPH = ("Henüz bir simülasyon çalıştırılmadığı için", "No simulation has been run yet")
VIOL = ("UNGROUNDED", "SCALE_VIOLATION", "UNIT_MISMATCH")
DEC_ALT = r"\d{1,3}[.,]\d{4,}(?![.,]?\d)|"
LONG_DEC = re.compile(r"\d{1,3}[.,]\d{4,}")


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _jl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def _dump(name: str, obj) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"-> {OUT / name}")


# ── matcher variants ───────────────────────────────────────────────────────────

def _v5():
    from experiments.gfp_benchmark import sens_v225_v5 as v5
    return v5


def dec_re():
    import app.llm.provenance_guard as pg
    pat = pg._NUM_RE.pattern
    assert pat.count("(?P<num>") == 1
    return re.compile(pat.replace("(?P<num>", "(?P<num>" + DEC_ALT, 1), pg._NUM_RE.flags)


@contextlib.contextmanager
def variant(name: str):
    """Install a matcher variant in memory; restore the frozen one on exit."""
    assert name in ALL_VARIANTS, name
    import app.llm.provenance_guard as pg
    v5 = _v5()
    saved = (pg.ProvenanceGraph.check_response, pg._NUM_RE, v5._NUM_RE)
    try:
        if name in ("sign", "both"):
            pg.ProvenanceGraph.check_response = v5.ProvenanceGraphV5.check_response
        if name in ("decimal", "both"):
            r = dec_re()
            pg._NUM_RE = r
            v5._NUM_RE = r
        yield
    finally:
        pg.ProvenanceGraph.check_response, pg._NUM_RE, v5._NUM_RE = saved


def check_hashes() -> dict:
    h = {"guard": _sha(APP / "provenance_guard.py"), "orchestrator": _sha(APP / "ollama_orchestrator.py"),
         "v5_copy": _sha(HERE / "sens_v225_v5.py"), "this_script": _sha(Path(__file__))}
    assert h["guard"] == GUARD_SHA, "frozen guard changed"
    assert h["orchestrator"] == ORCH_SHA, "frozen orchestrator changed"
    assert h["v5_copy"] == V5_SHA, "v5 copy differs from platform a477e0eb"
    return h


# ── text helpers (shared by S2, S5, S6, S7) ────────────────────────────────────

def numeral_tags(text: str) -> Counter:
    """Frozen-regex numerals in text: how many are minus-prefixed (claim_sign) and how many are long decimals."""
    import app.llm.provenance_guard as pg
    v5 = _v5()
    c = Counter()
    for s in pg._split_sentences(text or ""):
        for m in pg._NUM_RE.finditer(s):
            c["numerals"] += 1
            c["minus_prefixed"] += int(v5.claim_sign(s, m.start("num")) == -1)
        c["long_decimal"] += sum(1 for m in dec_re().finditer(s) if LONG_DEC.fullmatch(m.group("num")))
    return c


def claim_positions(text: str, claims) -> list[tuple[str, int]] | None:
    """(sentence, start of digits) for each frozen claim, by re-scanning with the frozen regex. The frozen
    check_response appends exactly one claim per regex match, in order; None if that does not hold."""
    import app.llm.provenance_guard as pg
    pos = [(s, m.start("num")) for s in pg._split_sentences(text or "") for m in pg._NUM_RE.finditer(s)]
    return pos if len(pos) == len(claims) else None


def tag_numbered(prefix: str) -> str | None:
    """S6: tag of the numeral that ends `prefix` (the text before an audit marker '[#n]')."""
    import app.llm.provenance_guard as pg
    v5 = _v5()
    nums = list(pg._NUM_RE.finditer(prefix))
    if not nums:
        return None
    last = nums[-1]
    if v5.claim_sign(prefix, last.start("num")) == -1:
        return "signed"
    dm = [x for x in dec_re().finditer(prefix) if LONG_DEC.fullmatch(x.group("num"))]
    if dm and dm[-1].end() >= last.end():
        return "long_decimal"
    return None


# ── graphs ─────────────────────────────────────────────────────────────────────

class Sim:
    """Deterministic tool execution with an in-process cache keyed by (tool, args, stakeholder)."""

    def __init__(self):
        from app.llm import ollama_orchestrator as oo
        self.orch = oo.OllamaOrchestrator()
        self.cache: dict = {}
        self.ref: dict = {}

    def tool(self, tool, args, stk):
        key = json.dumps([tool, args, stk], sort_keys=True, ensure_ascii=False, default=str)
        if key not in self.cache:
            try:
                self.cache[key] = self.orch._execute_tool(tool, copy.deepcopy(args), stk)
            except Exception as exc:  # the live orchestrator would have recorded inputs only
                self.cache[key] = {"status": "simulation_failed", "error": repr(exc)}
        return self.cache[key]

    def ref_graph(self, q):
        """The run-time reference builder (run_benchmark._reference_graph), cached per question id."""
        if q["id"] not in self.ref:
            from experiments.gfp_benchmark.run_benchmark import _reference_graph
            g, ok, _ = _reference_graph(q, self.orch)
            self.ref[q["id"]] = g if ok else None
        return self.ref[q["id"]]

    def inrun_graph(self, q, traces: list[list[dict]]):
        """In-run graph as the live orchestrator builds it: every call added, failed calls with inputs only.
        A later MT turn starts from the stored, capped records (records_as_dicts)."""
        from app.llm.provenance_guard import ProvenanceGraph
        from experiments.gfp_benchmark.run_benchmark import _stk
        stk = _stk(q["stakeholder"])
        g = ProvenanceGraph()
        for i, steps in enumerate(traces):
            if i > 0:
                prev, g = g, ProvenanceGraph()
                g.load_records(prev.records_as_dicts())
            for st in steps or []:
                args = st.get("args") or {}
                g.add_tool_result(st.get("tool"), args, stk, self.tool(st.get("tool"), args, stk))
        return g


def _units(rec: dict) -> list[tuple[str, dict, list]]:
    """Scorable units of a trace: (label, unit dict, in-run tool traces up to this unit)."""
    if "turns" in rec:
        out, acc = [], []
        for i, t in enumerate(rec.get("turns") or []):
            acc = acc + [((t.get("provenance") or {}).get("tool_trace") or [])]
            out.append((f"t{i + 1}", t, list(acc)))
        return out
    return [("t1", rec, [((rec.get("provenance") or {}).get("tool_trace") or [])])]


def _rep_dict(rep, with_claims: bool) -> dict:
    d = {"counts": rep.counts, "passed": rep.passed, "ambiguous_matches": rep.ambiguous_matches}
    if with_claims:
        d["claims"] = [c.to_dict() for c in rep.claims]
        d["violations"] = list(rep.violations)
    return d


# ── rescore: S0, S2, S4, S5 + variant copies ───────────────────────────────────

class Acc:
    def __init__(self):
        self.gate = defaultdict(Counter)
        self.fail_examples: list = []
        self.s2 = defaultdict(lambda: defaultdict(Counter))
        self.s4 = defaultdict(Counter)
        self.s4_list: list = []
        self.s5: list = []
        self.s5_position_fallback = 0

    def tally(self, key: str, text: str, reps: dict) -> None:
        slot = self.s2[key]
        slot["_n"]["units"] += 1
        slot["_n"].update(numeral_tags(text))
        for v in VARIANTS:
            slot[v].update(reps[v].counts)
            slot[v]["units_counts_changed"] += int(reps[v].counts != reps["frozen"].counts)
            slot[v]["units_passed_to_failed"] += int(reps["frozen"].passed and not reps[v].passed)
            slot[v]["units_failed_to_passed"] += int(not reps["frozen"].passed and reps[v].passed)
        if "sign" in reps and len(reps["sign"].claims) == len(reps["frozen"].claims):
            slot["frozen>sign"].update(f"{a.verdict}>{b.verdict}" for a, b in
                                       zip(reps["frozen"].claims, reps["sign"].claims) if a.verdict != b.verdict)


def process_trace(rec: dict, fkey: str, sim, acc: Acc) -> dict | None:
    """Score one trace under all variants; return {variant: rescored copy}, or None if the reference gate fails."""
    q, arm = rec.get("question") or {}, rec.get("config")
    new = {v: copy.deepcopy(rec) for v in VARIANTS}
    drop = False
    v5 = _v5()
    for ui, (label, u, traces) in enumerate(_units(rec)):
        nu = {v: _units(new[v])[ui][1] for v in VARIANTS}
        prov = u.get("provenance")
        ref = u.get("reference_check") or {}
        ex = {"file": fkey, "qid": q.get("id"), "arm": arm, "rep": rec.get("repeat"), "unit": label}
        # reference stage: delivered text vs reference graph
        if ref.get("counts") is not None and u.get("reply"):
            g = sim.ref_graph(q)
            reps = {}
            for v in VARIANTS:
                with variant(v):
                    reps[v] = g.check_response(u["reply"]) if g is not None else None
            if reps["frozen"] is None or reps["frozen"].counts != ref["counts"]:
                acc.gate[fkey]["ref_fail"] += 1
                drop = True
                if len(acc.fail_examples) < 40:
                    acc.fail_examples.append({**ex, "stage": "ref", "stored": ref.get("counts"),
                                              "recomputed": reps["frozen"].counts if reps["frozen"] else None})
            else:
                acc.gate[fkey]["ref_ok"] += 1
                for v in VARIANTS:
                    nu[v]["reference_check"] = {**ref, **_rep_dict(reps[v], False)}
                acc.tally(f"{fkey}|{arm}|delivered_ref", u["reply"], reps)
        # in-run stages: delivered text and first draft vs the rebuilt in-run graph
        if prov is None:
            continue
        gi = sim.inrun_graph(q, traces)
        pre = prov.get("pre_intervention") or {}
        stages = [("delivered_inrun", u.get("reply"), prov.get("counts"))]
        if pre.get("reply") and pre.get("counts") is not None:
            stages.append(("draft_inrun", pre.get("reply"), pre.get("counts")))
        ok_all, by_stage = True, {}
        for stage, text, stored in stages:
            if stored is None or text is None:
                continue
            reps = {}
            for v in VARIANTS:
                with variant(v):
                    reps[v] = gi.check_response(text)
            if reps["frozen"].counts != stored:
                acc.gate[fkey][f"{stage}_fail"] += 1
                ok_all = False
                if len(acc.fail_examples) < 40:
                    acc.fail_examples.append({**ex, "stage": stage, "stored": stored,
                                              "recomputed": reps["frozen"].counts})
            else:
                acc.gate[fkey][f"{stage}_ok"] += 1
                by_stage[stage] = (text, reps)
        if not ok_all:
            for v in VARIANTS:
                nu[v].setdefault("provenance", {})["_sens_inrun_unscored"] = True
            continue
        for stage, (text, reps) in by_stage.items():
            acc.tally(f"{fkey}|{arm}|{stage}", text, reps)
        for v in VARIANTS:
            np_ = nu[v]["provenance"]
            if "delivered_inrun" in by_stage:
                np_.update(_rep_dict(by_stage["delivered_inrun"][1][v], True))
            if "draft_inrun" in by_stage:
                np_["pre_intervention"] = {**pre, **_rep_dict(by_stage["draft_inrun"][1][v], False)}
        if arm != "grounded_guard":
            continue
        # S4: block attribution (lower bound) + delivered summaries failing their own check
        k = f"{fkey}|{label}"
        acc.s4[k]["evaluated"] += 1
        acc.s4[k]["blocked"] += int(bool(prov.get("blocked")))
        if prov.get("retried") and "draft_inrun" in by_stage:
            acc.s4[k]["retried"] += 1
            for v in VARIANTS[1:]:
                passes = by_stage["draft_inrun"][1][v].passed
                acc.s4[k][f"retried_draft_passes_{v}"] += int(passes)
                acc.s4[k][f"blocked_draft_passes_{v}"] += int(passes and bool(prov.get("blocked")))
        if "delivered_inrun" in by_stage:
            text, reps = by_stage["delivered_inrun"]
            if prov.get("blocked") and not reps["frozen"].passed:
                acc.s4[k]["summary_fails_own_check"] += 1
                acc.s4_list.append({**ex, "flagged": [(c.text, c.verdict, c.sentence[:100])
                                                      for c in reps["frozen"].claims if c.verdict in VIOL],
                                    "passes_under": [v for v in VARIANTS[1:] if reps[v].passed]})
            # S5: fail-open — minus-prefixed claims the frozen matcher GROUNDED
            recs = {r.key: r.value for r in gi.records}
            pos = claim_positions(text, reps["frozen"].claims)
            if pos is None:
                acc.s5_position_fallback += 1
            for i, c in enumerate(reps["frozen"].claims):
                if c.verdict != "GROUNDED":
                    continue
                s, start = pos[i] if pos else (c.sentence, max(c.sentence.find(c.text), 0))
                if v5.claim_sign(s, start) == -1:
                    rv = recs.get(c.matched_key)
                    acc.s5.append({**ex, "blocked": bool(prov.get("blocked")), "claim": c.text,
                                   "matched_key": c.matched_key, "record_value": rv,
                                   "record_sign": None if rv is None else (1 if rv >= 0 else -1),
                                   "sentence": c.sentence[:160]})
    if drop:
        acc.gate[fkey]["traces_dropped"] += 1
        return None
    return new


def rescore(runs: list[str]) -> None:
    check_hashes()
    self_test()
    sim, acc = Sim(), Acc()
    for run in runs:
        pats = RUNS.get(run, ["raw_g1_*.jsonl", "raw_mt_*.jsonl"])
        files = sorted({Path(p) for pat in pats for p in glob.glob(str(RES / run / pat))})
        for f in files:
            rows = _jl(f)
            fkey = f"{run}|{f.name}"
            print(f"{fkey}: {len(rows)} traces", flush=True)
            copies = {v: [] for v in VARIANTS}
            for rec in rows:
                new = process_trace(rec, fkey, sim, acc)
                if new is not None:
                    for v in VARIANTS:
                        copies[v].append(new[v])
            for v in VARIANTS:
                d = WORK / v / run
                d.mkdir(parents=True, exist_ok=True)
                (d / f.name).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in copies[v]),
                                        encoding="utf-8")
        _copy_support(run)
    _dump("gate.json", {"hashes": check_hashes(), "variants": VARIANTS, "per_file": acc.gate,
                        "fail_examples": acc.fail_examples})
    if DRYRUN:
        print("dry run: S2/S4/S5 not written")
        return
    _dump("s2_incidence.json", {k: {v: dict(c) for v, c in d.items()} for k, d in acc.s2.items()})
    _dump("s4_block_attribution.json", {"per_unit": acc.s4, "summaries_failing_own_check": acc.s4_list,
                                        "note": "lower bound: retry text of blocked turns is not stored"})
    _dump("s5_fail_open.json", {"items": acc.s5, "position_fallbacks": acc.s5_position_fallback})


def _copy_support(run: str) -> None:
    """Copy the allowlisted non-trace files the S3 jobs read (never coder files, the blinding key or *.log)."""
    for v in VARIANTS:
        for pat in SUPPORT.get(run, []):
            for p in glob.glob(str(RES / run / pat)):
                rel = Path(p).relative_to(RES / run)
                (WORK / v / run / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, WORK / v / run / rel)


# ── strings: S1, S6, S7 (no simulator) ─────────────────────────────────────────

def strings() -> None:
    check_hashes()
    # S1 — P3 split, guard arm
    s1 = defaultdict(Counter)
    for run in RUNS:
        for pat in RUNS[run]:
            for f in sorted(glob.glob(str(RES / run / pat))):
                for rec in _jl(Path(f)):
                    if rec.get("config") != "grounded_guard" or rec.get("fallback") or rec.get("error"):
                        continue
                    for label, u, _ in _units(rec):
                        prov = u.get("provenance") or {}
                        if not prov.get("blocked"):
                            continue
                        k = f"{run}|{Path(f).name}|{label}"
                        reply = u.get("reply") or ""
                        trace = prov.get("tool_trace") or []
                        s1[k]["blocked"] += 1
                        if any(m in reply for m in EMPTY_SUMMARY):
                            s1[k]["records_but_empty_summary"] += 1
                            if not trace:
                                s1[k]["records_but_empty_summary|no_call_this_unit"] += 1
                            else:
                                last = trace[-1] or {}
                                s1[k][f"records_but_empty_summary|last={last.get('tool')}"
                                      f"|failed={bool(last.get('failed'))}"] += 1
                        elif any(m in reply for m in EMPTY_GRAPH):
                            s1[k]["empty_graph"] += 1
                        else:
                            s1[k]["summary_with_numbers"] += 1
    _dump("s1_p3_split.json", s1)

    # S6 — A22 audit numerals: signed / >=4-decimal, x matcher verdict, x coder-1 labels
    import csv
    adir = RES / "oct_v42" / "audit"
    key = {(r["item"], r["number"]): r for r in csv.DictReader(open(adir / "audit_key.csv", encoding="utf-8-sig"))}
    c1 = {(r["item"], r["number"]): r for r in
          csv.DictReader(open(RES / "oct_v42" / "coded" / "audit_coded_coder1.csv", encoding="utf-8-sig"))}
    s6, s6_list = Counter(), []
    for it in _jl(adir / "audit_items.jsonl"):
        text = it.get("delivered_numbered") or ""
        for m in re.finditer(r"\[#(\d+)\]", text):
            prefix = text[max(0, m.start() - 60):m.start()].rstrip()
            tag = tag_numbered(prefix)
            if tag:
                k = (it["item"], m.group(1))
                kv, cv = key.get(k, {}), c1.get(k, {})
                s6[f"{tag}|{kv.get('matcher_verdict')}|traceable={cv.get('traceable_YN')}"] += 1
                s6_list.append({"item": k[0], "number": k[1], "tag": tag, "path": kv.get("path"),
                                "condition": kv.get("condition"), "matcher_verdict": kv.get("matcher_verdict"),
                                "coder1_traceable": cv.get("traceable_YN"), "context": prefix[-50:]})
    _dump("s6_audit.json", {"counts": s6, "items": s6_list})

    # S7 — G4 corpus
    s7, s7_ex = Counter(), []
    for f in sorted(glob.glob(str(RES / "raw_g4_final*.jsonl"))):
        for rec in _jl(Path(f)):
            for field in ("source", "mutated"):
                t = numeral_tags(rec.get(field) or "")
                for tag in ("minus_prefixed", "long_decimal"):
                    if t[tag]:
                        s7[f"{Path(f).name}|{field}|{tag}"] += t[tag]
                        if len(s7_ex) < 200:
                            s7_ex.append({"file": Path(f).name, "field": field, "tag": tag, "n": t[tag],
                                          "kind": rec.get("kind"), "category": rec.get("category"),
                                          "qid": rec.get("qid")})
    _dump("s7_g4_corpus.json", {"counts": s7, "examples": s7_ex})


# ── analyze: S3 (frozen analyses on variant copies, patched matcher) ───────────

G1_MODELS = ["raw_g1_gemma4-e4b_2026*T*.jsonl", "raw_g1_qwen3.8-27b_2026*T*.jsonl",
             "raw_g1_mistral-small3.2-24b_2026*.jsonl", "raw_g1_muse-glimmer-30b_2026*.jsonl",
             "raw_g1_gemma4-e4b_en_*.jsonl", "raw_g1_qwen3.8-27b_en_*.jsonl"]


def _pick(d: Path, pat: str) -> str | None:
    """The file the frozen analyses would pick for a G1 condition: the largest match (TR globs exclude _en_)."""
    hits = sorted(glob.glob(str(d / pat)), key=lambda p: Path(p).stat().st_size)
    hits = [h for h in hits if ("_en_" in h) == ("_en_" in pat)]
    return hits[-1] if hits else None


def _jobs(v: str) -> list[tuple[str, dict, list[str]]]:
    w = f"{OUT.name}/_work/{v}"
    g1 = WORK / v / "oct_v42"
    jobs = []
    for pat in G1_MODELS:
        f = _pick(g1, pat)
        if f:
            jobs.append((f"gfs_{Path(f).stem.replace('raw_g1_', '')}", {},
                         ["experiments.gfp_benchmark.compute_gfs", f]))
    core = [_pick(g1, p) for p in G1_MODELS[:2]]
    jobs.append(("gfs_pooled_tr_core", {}, ["experiments.gfp_benchmark.compute_gfs", "--pooled-sensitivity", *core]))
    jobs += [
        ("paths", {"GFP_RUN_DIR": f"{w}/oct_v42"}, ["experiments.gfp_benchmark.intervention_paths"]),
        ("rescore", {"GFP_RUN_DIR": f"{w}/oct_v42"}, ["experiments.gfp_benchmark.rescore_crosslingual"]),
        ("crosslingual_stats", {"GFP_RUN_DIR": f"{w}/oct_v42"}, ["experiments.gfp_benchmark.crosslingual_stats"]),
        ("taxonomy", {"GFP_RUN_DIR": f"{w}/oct_v42"}, ["experiments.gfp_benchmark.analyze_guard_flag_taxonomy"]),
        ("mt_analysis", {"GFP_RUN_DIR": f"{w}/oct_v42", "GFP_MT_DIR": f"{w}/oct_v42_mt"},
         ["experiments.gfp_benchmark.multiturn_analysis", "analyze"]),
        # a30_analysis sets its MT G1_RUN to results/oct_v42 itself; it only reads tu_proxy_validation.json there
        ("a30_analysis", {"GFP_RUN_DIR": f"{w}/oct_v42_evren"}, ["experiments.gfp_benchmark.a30_analysis"]),
    ]
    return jobs


def analyze(variants: tuple) -> None:
    check_hashes()
    for v in variants:
        od = OUT / "analysis" / v
        od.mkdir(parents=True, exist_ok=True)
        for name, env, argv in _jobs(v):
            cmd = [sys.executable, "-m", "experiments.gfp_benchmark.sens_v225", "exec", v, *argv]
            print(f"[{v}] {name}: {' '.join(argv[1:])} {env}", flush=True)
            with open(od / f"{name}.out", "w", encoding="utf-8") as fo, \
                    open(od / f"{name}.err", "w", encoding="utf-8") as fe:
                rc = subprocess.call(cmd, env={**os.environ, **env}, stdout=fo, stderr=fe,
                                     cwd=str(HERE.parent.parent))
            print(f"    exit {rc}", flush=True)


def exec_patched(v: str, module: str, args: list[str]) -> None:
    check_hashes()
    with variant(v):
        sys.argv = [module, *args]
        runpy.run_module(module, run_name="__main__", alter_sys=True)


# ── tests ──────────────────────────────────────────────────────────────────────

def self_test() -> None:
    """Pins the variants on fixed strings (fails loudly if a variant does not behave as declared)."""
    from app.llm.provenance_guard import ProvenanceGraph
    g = ProvenanceGraph()
    g.load_records([{"key": "npv_tl", "value": -588031.51, "scale": "building", "unit": "TL"},
                    {"key": "electricity_buy_price_tl_per_kwh", "value": 4.676, "scale": "building",
                     "unit": ""},  # unit-agnostic record, as in the observed "-4,676 TL" fail-open case
                    {"key": "max_voltage_pu", "value": 1.1015, "scale": "feeder", "unit": "pu"}])

    def verdicts(text):
        return [(c.text, c.verdict) for c in g.check_response(text).claims]

    s_neg, s_unsigned, s_fo, s_dec = ("Net present value: -588,032 TL", "Net present value: 588,032 TL",
                                      "Net present value: -4,676 TL", "Max voltage 1.1015 pu")
    with variant("frozen"):
        assert verdicts(s_neg)[0][1] == "UNGROUNDED", verdicts(s_neg)
        assert verdicts(s_fo)[0][1] == "GROUNDED", verdicts(s_fo)       # fail-open, frozen
        assert len(verdicts(s_dec)) == 2, verdicts(s_dec)               # split: "1.101" + "5"
    with variant("sign"):
        assert verdicts(s_neg)[0][1] == "GROUNDED", verdicts(s_neg)
        assert verdicts(s_unsigned)[0][1] != "GROUNDED", verdicts(s_unsigned)
        assert verdicts(s_fo)[0][1] != "GROUNDED", verdicts(s_fo)
        assert len(verdicts(s_dec)) == 2, verdicts(s_dec)
    with variant("decimal"):
        assert verdicts(s_dec) == [("1.1015", "GROUNDED")], verdicts(s_dec)
        assert verdicts(s_neg)[0][1] == "UNGROUNDED", verdicts(s_neg)
        r = dec_re()
        # "1,234.5678": thousands group + >=4 decimals is outside the declared rule; it keeps the frozen split.
        for t, tok in (("1.234,56 TL", "1.234,56"), ("1,234.5678", "1,234.567"), ("2026.1234", "2026.1234"),
                       ("12.3456", "12.3456"), ("1.234.567", "1.234.567"), ("0,9683 pu", "0,9683")):
            assert r.search(t).group("num") == tok, (t, r.search(t).group("num"))
    with variant("both"):
        assert verdicts(s_neg)[0][1] == "GROUNDED" and verdicts(s_dec) == [("1.1015", "GROUNDED")]
    with variant("frozen"):                                             # restored
        assert verdicts(s_neg)[0][1] == "UNGROUNDED" and len(verdicts(s_dec)) == 2
    assert tag_numbered("Net bugünkü değer: -588.032 TL") == "signed"
    assert tag_numbered("Maks. gerilim 1.1015") == "long_decimal"
    assert tag_numbered("Aralık 5-10") is None and tag_numbered("Gerilim 1.101") is None
    t = numeral_tags("NPV: -588,032 TL. Gerilim 1.1015 pu. Saat 12:00 - 16:00.")
    assert t["minus_prefixed"] == 1 and t["long_decimal"] == 1, t
    print("self-test OK")


def fixture_test() -> None:
    """Runs process_trace on a synthetic blocked guard-arm trace with a fake simulator, and checks S0/S2/S4/S5."""
    class FakeSim:
        def __init__(self):
            self.real = None

        def tool(self, tool, args, stk):
            return {"npv_tl": -588031.51, "electricity_buy_price_tl_per_kwh": 4.676}

        def ref_graph(self, q):
            return self.inrun_graph(q, [[{"tool": "simulate_pv_bess", "args": {"panel_kw": 5}}]])

        inrun_graph = Sim.inrun_graph

    sim = FakeSim()
    q = {"id": "fx-01", "stakeholder": "residential"}
    trace = [{"round": 1, "tool": "simulate_pv_bess", "args": {"panel_kw": 5}, "failed": False}]
    reply = "Simülasyon sonuçları:\n• Net bugünkü değer: -588,032 TL\n• Fiyat: -4,676 TL"
    draft = "Kurulum 5 kW. Net bugünkü değer -588,032 TL olur."
    with variant("frozen"):
        gi = sim.inrun_graph(q, [trace])
        st_reply, st_draft = gi.check_response(reply), gi.check_response(draft)
    rec = {"question": q, "config": "grounded_guard", "repeat": 0, "reply": reply,
           "reference_check": {"counts": st_reply.counts, "passed": st_reply.passed},
           "provenance": {"counts": st_reply.counts, "passed": st_reply.passed, "blocked": True, "retried": True,
                          "tool_trace": trace, "n_records": len(gi.records),
                          "pre_intervention": {"reply": draft, "counts": st_draft.counts,
                                               "passed": st_draft.passed}}}
    acc = Acc()
    new = process_trace(rec, "fixture|fx.jsonl", sim, acc)
    assert new is not None and acc.gate["fixture|fx.jsonl"]["ref_ok"] == 1, acc.gate
    assert acc.gate["fixture|fx.jsonl"]["delivered_inrun_ok"] == 1 and acc.gate["fixture|fx.jsonl"]["draft_inrun_ok"] == 1
    k = "fixture|fx.jsonl|t1"
    assert acc.s4[k]["summary_fails_own_check"] == 1, acc.s4
    assert acc.s4_list and acc.s4_list[0]["flagged"][0][0] == "588,032", acc.s4_list
    if "sign" in VARIANTS:
        assert acc.s4[k]["retried_draft_passes_sign"] == 1 and acc.s4[k]["blocked_draft_passes_sign"] == 1, acc.s4
        # the fail-open price line makes the summary fail under `sign`; the NPV line itself is now GROUNDED
        assert new["sign"]["reference_check"]["counts"]["GROUNDED"] >= 1
    assert [x["claim"] for x in acc.s5] == ["4,676"] and acc.s5[0]["record_sign"] == 1, acc.s5
    slot = acc.s2["fixture|fx.jsonl|grounded_guard|delivered_ref"]
    assert slot["_n"]["minus_prefixed"] == 2, slot
    # a reference-gate failure drops the trace
    bad = copy.deepcopy(rec)
    bad["reference_check"]["counts"] = {**st_reply.counts, "GROUNDED": 99}
    acc2 = Acc()
    assert process_trace(bad, "fixture|fx.jsonl", sim, acc2) is None and acc2.gate["fixture|fx.jsonl"]["traces_dropped"] == 1
    print("fixture test OK")


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    if cmd == "check":
        print(json.dumps(check_hashes(), indent=1))
        self_test()
        fixture_test()
    elif cmd == "rescore":
        runs = list(RUNS)
        if "--runs" in sys.argv:
            runs = sys.argv[sys.argv.index("--runs") + 1].split(",")
        fixture_test()
        rescore(runs)
    elif cmd == "strings":
        strings()
    elif cmd == "analyze":
        analyze(VARIANTS)
    elif cmd == "exec":
        exec_patched(sys.argv[2], sys.argv[3], sys.argv[4:])
    else:
        raise SystemExit(f"unknown command {cmd}")


if __name__ == "__main__":
    main()
