#!/usr/bin/env python3
"""Manuscript numeral audit (GFP paper).

Every numeral in the manuscript is checked, at the precision it is printed with,
against the released sources. The check is scoped, because a single global pool of
output values is so dense that almost any number matches it by chance.

  scoped        a results section is checked only against the analysis summaries
                that produce it (SCOPES below). Each match is also tested with four
                decoys (the numeral shifted by +-3 and +-7 units in its last printed
                digit). A match is "decoy-robust" when at most one decoy also matches.
  code/design   checked against the pre-registered (hash-frozen) code files and the
                pre-registration documents. Used first for the parameter appendix and
                the design sections, and as a fallback elsewhere.
  consistent    abstract, introduction, discussion, conclusion and the extra documents
                (highlights, cover letter, graphical abstract) restate results. A
                numeral there is consistent if it equals, at its printed precision, a
                numeral that matched its scoped sources in a results section.
  union         matched only in the union of all analysis summaries (weaker).
  exception     neither; listed in exceptions.csv with a stated reason.
  UNEXPLAINED   none of the above. The audit is complete when this count is zero.

A numeral matches a source value v if it equals v, 100*v or v/100 after rounding to
the printed precision. Raw LLM traces (*.jsonl) and logs are never used as sources.

Standard library only; read-only except for report.md / report.json in this folder.
Usage:  python -I audit_numerals.py
"""
from __future__ import annotations

import argparse
import bisect
import csv
import json
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BENCH = HERE.parent                      # experiments/gfp_benchmark
BACKEND = BENCH.parent.parent            # laadt-dss/backend
REPO = BACKEND.parent.parent             # repository root
R = "results/"

# Analysis summaries per results section (globs relative to experiments/gfp_benchmark).
G3 = [R + "g3_all_feeders.json", R + "g3_all.json", R + "g3_rural1.json", "PREREGISTRATION_G3.md"]
G4 = [R + "g4_summary.json", R + "_v41_outputs_backup/g4_summary.json",
      R + "tolerance_sensitivity_g4.json", R + "oct_v42/analysis/tol_g4.out",
      R + "oct_v42/a26/a26_results.json", R + "oct_v42/a26/a26_results.md",
      R + "oct_v42/a26_build_stdout.txt", R + "a25_jev_summary.json",
      R + "regression_v41_v42.json", R + "regression_clearsky_replay.json",
      R + "oct_v42/audit/audit_jev_stdout.txt", "b4_mutation_quality/B4_results.json",
      R + "a23_legacy_decomposition.json"]
G1 = [R + "oct_v42/intervention_paths.json", R + "oct_v42/guard_coverage.json",
      R + "oct_v42/g1_reachable_subset.json", R + "oct_v42/determinism_identity.json",
      R + "oct_v42/tolerance_sensitivity_g1.json", R + "oct_v42/trap_analysis.json",
      R + "oct_v42/crosslingual_stats.json", R + "oct_v42/crosslingual_rescore.json",
      R + "oct_v42/analysis/*.out", R + "oct_v42/analysis/*.txt",
      R + "oct_v42/audit/a22_results.json", R + "oct_v42/audit/tu_proxy_validation.json"]
MT = [R + "oct_v42_mt/mt_results.json", R + "oct_v42_mt/mt_analysis.out",
      R + "oct_v42/audit/tu_proxy_validation.json"]
TAX = [R + "guard_flag_taxonomy.json", R + "oct_v42/tolerance_sensitivity_taxonomy.json",
       R + "oct_v42/tolerance_sensitivity_taxonomy.A_TR_only.json",
       R + "oct_v42/analysis/taxonomy*.out", R + "oct_v42/analysis/tol_tax*.out",
       R + "oct_v42/analysis/taxonomy_regression_A_TR.txt"]
XL = G1 + G4 + [R + "crosslingual_stats.json", R + "analysis_gemma.json", R + "analysis_qwen.json"]
TOL = [R + "tolerance_sensitivity_g4.json", R + "oct_v42/tolerance_sensitivity_g1.json",
       R + "oct_v42/tolerance_sensitivity_taxonomy.json",
       R + "oct_v42/tolerance_sensitivity_taxonomy.A_TR_only.json",
       R + "oct_v42/analysis/tol_*.out"]
A30 = [R + "oct_v42_evren/*.json", R + "oct_v42_evren/README.md",
       R + "oct_v42_evren/analysis/*.out"] + G1 + MT   # App D compares against Model A (G1, G1-MT)
DERIVED = ["manuscript_audit/derived_values.json"]   # recomputed by derived_values.py
# Post-outcome matcher sensitivity (prereg-v3.8): stage outputs and the frozen/both re-analyses.
# Scoped to App E only, so a frozen/corrected mix-up in a primary number cannot pass; numbers the
# main text quotes from it come from derived_values.json (matcher_sensitivity), which every
# results scope already reads.
SENS = [R + "sens_v225/*.json", R + "sens_v225/analysis/frozen/*.out", R + "sens_v225/analysis/both/*.out",
        R + "sens_v225/analysis/frozen/*/*.json", R + "sens_v225/analysis/both/*/*.json"] + DERIVED
G1 += DERIVED
XL += DERIVED
G4 += DERIVED
MT += DERIVED
TAX += DERIVED
TOL += DERIVED
A30 += DERIVED
ALL_SUMMARIES = sorted(set(G3 + G4 + G1 + MT + TAX + XL + TOL + A30 + SENS + DERIVED + [
    R + "trap_analysis.json", R + "guard_coverage.json", R + "a25_evidence_items.json",
    R + "_v41_outputs_backup/*.json", R + "oct_v42/a26/*.json", R + "oct_v42/a26/*.md"]))

# (heading regex, scope name, mode, sources). mode: "scoped" | "design" | "restate"
SCOPES = [
    (r"\\begin\{document\}",                 "front matter",      "restate", []),
    (r"\\section\{Introduction\}",            "introduction",      "restate", []),
    (r"\\section\{Related Work\}",            "related work",      "restate", []),
    (r"\\section\{The Grounding Fidelity",    "protocol",          "design",  []),
    (r"\\section\{Platform and Experimental", "design",            "design",  []),
    (r"\\section\{Results\}",                 "results (intro)",   "restate", []),
    (r"\\label\{sec:g3\}",                    "G3",                "scoped",  G3),
    (r"\\label\{sec:g4\}",                    "G4",                "scoped",  G4),
    (r"\\label\{sec:g1\}",                    "G1",                "scoped",  G1),
    (r"\\label\{sec:g1mt\}",                  "G1-MT",             "scoped",  MT),
    (r"\\label\{sec:tax\}",                   "taxonomy",          "scoped",  TAX),
    (r"\\label\{sec:g2\}",                    "G2",                "scoped",  G1),
    (r"\\label\{sec:crosslingual\}",          "cross-lingual",     "scoped",  XL),
    (r"\\section\{Discussion\}",              "discussion",        "restate", []),
    (r"\\section\{Threats to Validity\}",     "threats",           "restate", []),
    (r"\\section\{Conclusion\}",              "conclusion",        "restate", []),
    (r"\\label\{app:lexicon\}",               "App A lexicon",     "design",  []),
    (r"\\label\{app:matcher\}",               "App B matcher",     "scoped",  SENS),
]

# Supplementary Material (v2.28 length cut): text moved verbatim from the article keeps the
# audit mode and sources it had there. Read in the same run as the article, so the
# "consistent" check of restating lines sees results numerals from both files.
SUPP_SCOPES = [
    (r"\\begin\{document\}",                 "S preamble",        "restate", []),
    (r"\\label\{sup:protocol\}",             "S1 protocol",       "design",  []),
    (r"\\label\{sup:params\}",               "S2 parameters",     "design",  []),
    (r"\\label\{sup:prereg\}",               "S3 prereg/history", "restate", []),
    (r"\\label\{sup:g3\}",                   "S4 G3",             "scoped",  G3),
    (r"\\label\{sup:g4\}",                   "S5 G4",             "scoped",  G4),
    (r"\\label\{sup:g1\}",                   "S6 G1",             "scoped",  G1),
    (r"\\label\{sup:mt\}",                   "S7 G1-MT",          "scoped",  MT),
    (r"\\label\{sup:tax\}",                  "S8 taxonomy",       "scoped",  TAX),
    (r"\\label\{sup:tolerance\}",            "S9 tolerance",      "scoped",  TOL),
    (r"\\label\{sup:a30\}",                  "S10 A30",           "scoped",  A30),
    (r"\\label\{sup:limits\}",               "S11 threats (ext.)", "restate", []),
]

EXCLUDE_NAMES = {"rerun.log"}            # never read (standing instruction)

NUM_TXT = re.compile(r"(?<![\w.])-?(?:\d{1,3}(?:,\d{3})+|\d+)?(?:\.\d+)?(?:[eE][-+]?\d+)?")
NUM_CELL = re.compile(r"\s*-?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?\s*%?\s*")


def _to_float(tok: str):
    tok = tok.replace(",", "").strip()
    if not tok or tok in {"-", ".", "-."}:
        return None
    try:
        v = float(tok)
    except ValueError:
        return None
    return v if math.isfinite(v) else None


def _walk_json(obj, out):
    if isinstance(obj, bool) or obj is None:
        return
    if isinstance(obj, (int, float)):
        if math.isfinite(obj):
            out.append(float(obj))
    elif isinstance(obj, str):
        if NUM_CELL.fullmatch(obj):
            v = _to_float(obj.replace("%", ""))
            if v is not None:
                out.append(v)
    elif isinstance(obj, dict):
        for val in obj.values():
            _walk_json(val, out)
    elif isinstance(obj, (list, tuple)):
        for val in obj:
            _walk_json(val, out)


def numbers_in_text(text: str):
    return [v for v in (_to_float(m.group(0)) for m in NUM_TXT.finditer(text)) if v is not None]


def numbers_in_file(path: Path):
    try:
        if path.suffix == ".json":
            vals = []
            _walk_json(json.loads(path.read_text(encoding="utf-8")), vals)
            return vals
        return numbers_in_text(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        print(f"  [skip unreadable] {path}: {exc}", file=sys.stderr)
        return []


def resolve(globs):
    files = []
    for g in globs:
        for p in sorted(BENCH.glob(g)):
            if p.is_file() and p.name not in EXCLUDE_NAMES and p.suffix not in {".log", ".jsonl"}:
                files.append(p)
    return sorted(set(files))


def design_files():
    prereg = BENCH / "PREREGISTRATION.md"
    paths = set(re.findall(r"`((?:app|tests|experiments)/[\w/.\-]+)`",
                           prereg.read_text(encoding="utf-8")))
    files = [BACKEND / rel for rel in sorted(paths)
             if (BACKEND / rel).is_file() and (BACKEND / rel).suffix in {".py", ".json"}]
    for doc in ("PREREGISTRATION.md", "PREREGISTRATION_G3.md", "MULTITURN_DESIGN.md",
                "QUESTION_INPUTS.md", "SCALE_CODEBOOK.md", "AUDIT_CODEBOOK.md",
                "questions.json", "answer_keys.json", "multiturn_turn2.json"):
        if (BENCH / doc).is_file():
            files.append(BENCH / doc)
    return sorted(set(files))


class Pool:
    """Sorted absolute values with the file each came from."""

    def __init__(self, files, label):
        self.label = label
        self.files = [str(f.relative_to(REPO)).replace("\\", "/") for f in files]
        pairs = sorted((abs(v), i) for i, f in enumerate(files) for v in numbers_in_file(f))
        self.vals = [p[0] for p in pairs]
        self.idx = [p[1] for p in pairs]

    def find(self, lo, hi):
        i = bisect.bisect_left(self.vals, lo)
        j = bisect.bisect_right(self.vals, hi)
        if i >= j:
            return None
        cand = sorted({self.files[self.idx[k]] for k in range(i, min(j, i + 200))},
                      key=lambda s: ("backup" in s, len(s)))
        return cand[0]

    def __len__(self):
        return len(self.vals)


class GroupIndex:
    """Small co-location groups: every JSON object/list with at most GROUP_MAX numeric
    leaves, and every window of TEXT_WINDOW consecutive lines of a text output. A set of
    numerals printed on one manuscript line is co-located if one group holds them all."""

    GROUP_MAX = 80
    TEXT_WINDOW = 4

    def __init__(self, files):
        self.names = []
        pairs = []
        for f in files:
            rel = str(f.relative_to(BENCH)).replace("\\", "/")
            for label, vals in self._groups(f):
                gid = len(self.names)
                self.names.append(f"{rel}:{label}")
                pairs.extend((abs(v), gid) for v in set(vals))
        pairs.sort()
        self.vals = [p[0] for p in pairs]
        self.gid = [p[1] for p in pairs]

    def _groups(self, f):
        if f.suffix == ".json":
            try:
                obj = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return
            yield from self._json_groups(obj, "$")
        else:
            lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
            nums = [numbers_in_text(ln) for ln in lines]
            for i in range(len(lines)):
                vals = [v for k in range(i, min(i + self.TEXT_WINDOW, len(lines))) for v in nums[k]]
                if vals:
                    yield f"L{i + 1}", vals

    def _json_groups(self, obj, path):
        """Yield (path, values) for every container with <= GROUP_MAX numeric leaves."""
        out = []
        if isinstance(obj, dict):
            items = obj.items()
        elif isinstance(obj, list):
            items = enumerate(obj)
        else:
            return
        for k, v in items:
            if isinstance(v, (dict, list)):
                sub = list(self._json_groups(v, f"{path}.{k}"))
                for g in sub:
                    yield g
                # the child's full value list is the last item it yielded, if small
            leaf = []
            _walk_json(v, leaf)
            out.extend(leaf)
        if 0 < len(out) <= self.GROUP_MAX:
            yield path, out

    def groups_with(self, v, dec, is_sci):
        x, h = abs(v), halfwidth(v, dec, is_sci)
        hit = set()
        for lo, hi in ((x - h, x + h), ((x - h) / 100.0, (x + h) / 100.0),
                       ((x - h) * 100.0, (x + h) * 100.0)):
            i = bisect.bisect_left(self.vals, lo)
            j = bisect.bisect_right(self.vals, hi)
            hit.update(self.gid[i:j])
        return hit


def colocate(index, nums):
    """nums: list of (v, dec, sci). Return (covered_mask, group_name) for the group that
    covers the most numerals (ties: first)."""
    sets = [index.groups_with(v, d, s) for v, d, s in nums]
    counts = {}
    for s in sets:
        for g in s:
            counts[g] = counts.get(g, 0) + 1
    if not counts:
        return [False] * len(nums), None
    best = max(counts, key=lambda g: (counts[g], -g))
    return [best in s for s in sets], index.names[best]


# ----------------------------------------------------------------- extraction
CMD_ARG = re.compile(r"\\(?:cite[pt]?|citeauthor|ref|eqref|autoref|label|url|input|include"
                     r"|includegraphics|texttt|hspace|vspace|cmidrule|cline|setlength"
                     r"|bibliography|bibliographystyle|bibitem|newcommand|renewcommand"
                     r"|counterwithin|definecolor|usepackage|documentclass|journal)\*?"
                     r"(?:\([^)]*\))?(?:\[[^\]]*\])?(?:\{(?:[^{}]|\{[^{}]*\})*\})+")
ENV_SPEC = re.compile(r"\\begin\{(?:tabular\*?|tabularx|array|table|figure)\*?\}"
                      r"(?:\[[^\]]*\])?(?:\{(?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*\})?")
MULTICOL = re.compile(r"\\multicolumn\{\d+\}\{(?:[^{}]|\{[^{}]*\})*\}")
LENGTH = re.compile(r"-?\d*\.?\d+\s*(?:cm|mm|pt|em|ex|bp)\b|\d*\.?\d+\\(?:linewidth|textwidth|columnwidth)")
ROWSKIP = re.compile(r"\\\\\[[^\]]*\]")
PCOL = re.compile(r"[pmb]\{[\d.]+(?:cm|mm|pt|em)\}")
SUBSCRIPT = re.compile(r"_\{[^{}]*\}|_\d+")
IDENT = re.compile(r"\b[A-Za-z][\w.:\-]*\d[\w.:\-]*|\b\d+[A-Za-z][\w.:\-]*")
DATE = re.compile(r"\b(?:19|20)\d{2}-\d{2}(?:-\d{2})?(?:T[\dZ:]+)?")
SCI = re.compile(r"(\d+(?:\.\d+)?)\s*(?:\{\\times\}|\\times|\{\\cdot\}|\\cdot)\s*10\^\{?\s*(-?\s*\d+)\s*\}?")
NUM_TEX = re.compile(r"(?<![\w.\\])(\d{1,3}(?:\{,\}\d{3})+(?:\.\d+)?|(?<![\d,])\d{1,3}(?:,\d{3})+(?![\d.,])|\d+\.\d+|\d+|\.\d+)(?![\w])")
TIKZ_SKIP = re.compile(r"^\s*\\(?:draw|fill|filldraw|clip|foreach|def|coordinate|ic[A-Z]|house|begin\{scope|end\{scope|hyphenpenalty)")
PARENS = re.compile(r"\([^()]*\)")
BRACKETS = re.compile(r"\[[^\[\]]*\]")


def clean_line(s: str, mode: str) -> str:
    if mode in ("tex", "tikz"):
        s = re.sub(r"(?<!\\)%.*", "", s)
        if mode == "tikz":
            if TIKZ_SKIP.match(s) or "/.style" in s or "tikzpicture" in s:
                return ""
            s = BRACKETS.sub(" ", PARENS.sub(" ", s))
        s = s.replace("\\_", "_")
        for rx in (CMD_ARG, ENV_SPEC, MULTICOL, ROWSKIP, PCOL, LENGTH, SUBSCRIPT):
            s = rx.sub(" ", s)
    s = DATE.sub(" ", s)
    return IDENT.sub(" ", s)


def extract(path: Path, mode: str):
    """Yield (line_no, raw_line, token, value, decimals, is_sci)."""
    lines = path.read_text(encoding="utf-8").splitlines()
    start = 0
    if mode in ("tex", "tikz"):
        for i, ln in enumerate(lines):
            if ln.strip().startswith("\\begin{document}"):
                start = i
                break
    for n in range(start, len(lines)):
        raw = lines[n]
        s = clean_line(raw, mode)
        for m in SCI.finditer(s):
            mant, exp = m.group(1), int(m.group(2).replace(" ", ""))
            dec = len(mant.split(".")[1]) if "." in mant else 0
            yield n + 1, raw, m.group(0), float(mant) * 10 ** exp, (dec, exp), True
        s = SCI.sub(" ", s)
        for m in NUM_TEX.finditer(s):
            tok = m.group(1)
            v = _to_float(tok.replace("{,}", ","))
            if v is None:
                continue
            dec = len(tok.split(".")[1]) if "." in tok else 0
            yield n + 1, raw, tok, v, dec, False


def halfwidth(v, dec, is_sci):
    if is_sci:
        d, exp = dec
        h = 0.5 * 10 ** (exp - d)
    else:
        h = 0.5 * 10 ** (-dec)
    return h + 1e-9 * max(1.0, abs(v))


def match(pool, v, dec, is_sci):
    x, h = abs(v), halfwidth(v, dec, is_sci)
    for lo, hi, how in ((x - h, x + h, "="),
                        ((x - h) / 100.0, (x + h) / 100.0, "x100"),
                        ((x - h) * 100.0, (x + h) * 100.0, "/100")):
        f = pool.find(lo, hi)
        if f:
            return f, how
    return None


def decoy_hits(pool, v, dec, is_sci):
    if is_sci:
        return 0
    unit = 10 ** (-dec)
    return sum(1 for k in (3, -3, 7, -7)
               if v + k * unit >= 0 and match(pool, v + k * unit, dec, False))


def load_exceptions(path: Path):
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as fh:
        return [r for r in csv.DictReader(fh) if r.get("value")]


def exception_for(rows, tok, raw, fname):
    norm = tok.replace("{,}", ",")
    for r in rows:
        if r.get("file") and r["file"] != fname:
            continue
        if r["value"].replace("{,}", ",") != norm:
            continue
        if r.get("context") and r["context"] not in raw:
            continue
        return r
    return None


def scope_of(lines_scopes, line):
    cur = lines_scopes[0]
    for s in lines_scopes:
        if s[0] <= line:
            cur = s
    return cur


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tex", default=str(REPO / "paper" / "main.tex"))
    ap.add_argument("--supp", default=str(REPO / "paper" / "supplement.tex"))
    ap.add_argument("--extra", nargs="*", default=[
        str(REPO / "paper" / "highlights.txt"),
        str(REPO / "paper" / "cover_letter.md"),
        str(REPO / "paper" / "figures" / "graphical_abstract.tex")])
    ap.add_argument("--exceptions", default=str(HERE / "exceptions.csv"))
    args = ap.parse_args()

    def starts_for(path, scopes):
        lines = path.read_text(encoding="utf-8").splitlines()
        out = []
        for rx, name, mode, srcs in scopes:
            for i, ln in enumerate(lines):
                if re.search(rx, ln):
                    out.append((i + 1, name, mode, srcs))
                    break
            else:
                sys.exit(f"scope heading not found in {path.name}: {rx}")
        return sorted(out)

    docs = [(Path(args.tex), SCOPES)]
    if args.supp and Path(args.supp).exists():
        docs.append((Path(args.supp), SUPP_SCOPES))
    doc_starts = [(p, starts_for(p, sc)) for p, sc in docs]

    pools, gindex = {}, {}
    for _, starts in doc_starts:
        for _, name, mode, srcs in starts:
            if mode == "scoped":
                pools[name] = Pool(resolve(srcs), name)
                gindex[name] = GroupIndex(resolve(srcs))
    design = Pool(design_files(), "code/design")
    union = Pool(resolve(ALL_SUMMARIES), "union")
    exc_rows = load_exceptions(Path(args.exceptions))

    records = []
    # pass 1: manuscript -- extract, then check scoped lines as co-located tuples
    for tex, scope_starts in doc_starts:
        for line, raw, tok, v, dec, sci in extract(tex, "tex"):
            start, sname, mode, _ = scope_of(scope_starts, line)
            records.append({"file": tex.name, "line": line, "scope": sname, "mode": mode,
                            "token": tok, "value": v, "dec": dec, "sci": sci,
                            "context": raw.strip()[:170], "status": "pending"})

    by_line = {}
    for r in records:
        if r["mode"] == "scoped":
            by_line.setdefault((r["scope"], r["file"], r["line"]), []).append(r)
    for (sname, _, _), recs in by_line.items():
        idx = gindex[sname]
        nums = [(r["value"], r["dec"], r["sci"]) for r in recs]
        if len(recs) >= 2:
            mask, gname = colocate(idx, nums)
            n_cov = sum(mask)
            if n_cov >= 2:
                for i, r in enumerate(recs):
                    if not mask[i]:
                        continue
                    still = 0
                    if not r["sci"]:
                        unit = 10 ** (-r["dec"])
                        for k in (3, -3, 7, -7):
                            dv = r["value"] + k * unit
                            if dv < 0:
                                continue
                            alt = list(nums)
                            alt[i] = (dv, r["dec"], False)
                            m2, _ = colocate(idx, alt)
                            if sum(m2) >= n_cov:
                                still += 1
                    r.update(status="co-located", source=gname, robust=still <= 1, decoys=still)
        for r in recs:
            if r["status"] != "pending":
                continue
            hit = match(pools[sname], r["value"], r["dec"], r["sci"])
            if hit:
                d = decoy_hits(pools[sname], r["value"], r["dec"], r["sci"])
                r.update(status="single", source=hit[0], transform=hit[1],
                         robust=d <= 1, decoys=d)
    for r in records:
        if r["status"] == "pending" and r["mode"] in ("design", "scoped"):
            hit = match(design, r["value"], r["dec"], r["sci"])
            if hit:
                r.update(status="code/design", source=hit[0], transform=hit[1])
    for r in records:
        if r["sci"]:
            r["dec"] = list(r["dec"])

    # restated numerals are compared with every results numeral that matched its scoped
    # sources (robust or not); the robustness of that body numeral is reported where it is
    body = [(r["value"], r["dec"], r["sci"]) for r in records
            if r["status"] in ("co-located", "single")]

    def consistent(v, dec, sci, pct):
        # exact value only; a printed percentage may also restate a fraction (x100)
        h = halfwidth(v, dec, sci)
        for b, _, _ in body:
            for bb in ((b, b * 100.0) if pct else (b,)):
                if abs(bb - abs(v)) <= h:
                    return True
        return False

    # pass 2: restating sections of the manuscript + extra documents
    extra = []
    for p in args.extra:
        path = Path(p)
        mode = "tikz" if path.suffix == ".tex" else "text"
        for line, raw, tok, v, dec, sci in extract(path, mode):
            extra.append({"file": path.name, "line": line, "scope": "restates results",
                          "token": tok, "value": v, "dec": dec if not sci else list(dec),
                          "sci": sci, "context": raw.strip()[:170], "status": "pending"})
    records += extra

    # restating lines: co-location against the union of all summaries
    union_g = GroupIndex(resolve(ALL_SUMMARIES))
    derived_pool = Pool(resolve(DERIVED), "derived")
    pend_lines = {}
    for r in records:
        if r["status"] == "pending":
            pend_lines.setdefault((r["file"], r["line"]), []).append(r)
    for recs in pend_lines.values():
        if len(recs) < 2:
            continue
        nums = [(r["value"], tuple(r["dec"]) if r["sci"] else r["dec"], r["sci"]) for r in recs]
        mask, gname = colocate(union_g, nums)
        n_cov = sum(mask)
        if n_cov < 2:
            continue
        for i, r in enumerate(recs):
            if not mask[i] or r["sci"]:
                continue
            still = 0
            unit = 10 ** (-r["dec"])
            for k in (3, -3, 7, -7):
                dv = r["value"] + k * unit
                if dv < 0:
                    continue
                alt = list(nums)
                alt[i] = (dv, r["dec"], False)
                if sum(colocate(union_g, alt)[0]) >= n_cov:
                    still += 1
            if still <= 1:
                r.update(status="co-located", source=gname, robust=True, decoys=still)

    line_vals = {}
    for r in records:
        line_vals.setdefault((r["file"], r["line"]), []).append(r["value"])

    def ratio_of_line(r, h):
        vals = [b for b in line_vals.get((r["file"], r["line"]), []) if b >= 1 and b != r["value"]]
        for a in vals:
            for b in vals:
                if a < b and abs(100.0 * a / b - r["value"]) <= h:
                    return f"{a:g}/{b:g}"
        return None

    for r in records:
        if r["status"] != "pending":
            continue
        v, dec, sci = r["value"], (tuple(r["dec"]) if r["sci"] else r["dec"]), r["sci"]
        pct = bool(re.search(re.escape(r["token"]) + r"\s*(?:\\%|%|\$?\\%)", r["context"]))
        e = exception_for(exc_rows, r["token"], r["context"], r["file"])
        if e:                           # explicit annotations take precedence over coincidences
            r.update(status="exception", source=e.get("category", ""), reason=e.get("reason", ""))
            continue
        dhit = None
        if sci or dec or v >= 10:       # also report a derived source, if there is one
            dhit = derived_pool.find(abs(v) - halfwidth(v, dec, sci), abs(v) + halfwidth(v, dec, sci))
        if consistent(v, dec, sci, pct):
            src = "equals a results numeral matched to its scoped sources"
            if dhit:
                src += "; also equals a value in derived_values.json"
            r.update(status="consistent", source=src)
            continue
        if dhit:
            r.update(status="derived", source=dhit)
            continue
        rat = ratio_of_line(r, halfwidth(v, dec, sci)) if pct and not sci else None
        if rat:
            r.update(status="derived", source=f"100 x {rat} of numerals on the same line")
            continue
        hit = match(design, v, dec, sci)
        if hit:
            r.update(status="code/design", source=hit[0], transform=hit[1])
            continue
        hit = match(union, v, dec, sci)
        if hit:
            st = "derived" if hit[0].endswith("derived_values.json") else "union"
            r.update(status=st, source=hit[0], transform=hit[1])
            continue
        r.update(status="UNEXPLAINED", source="")

    # ------------------------------------------------------------- report
    (HERE / "report.json").write_text(json.dumps(
        {"scopes": {n: pools[n].files for n in pools}, "design_files": design.files,
         "union_files": union.files, "records": records}, ensure_ascii=False, indent=1),
        encoding="utf-8")

    order = ["co-located", "single", "consistent", "derived", "code/design", "union", "exception", "UNEXPLAINED"]
    groups = [(n, mode) for _, st in doc_starts for _, n, mode, _ in st] + \
             [(Path(p).name, "extra") for p in args.extra]
    out = ["# Manuscript numeral audit", "",
           "Generated by `audit_numerals.py` (standard library, read-only); method in the "
           "script docstring. In brackets: decoy-robust matches (at most one of four shifted "
           "decoys also matches).", "",
           "| scope | mode | numerals | co-located [robust] | single [robust] | consistent | derived | code/design | union | exception | UNEXPLAINED |",
           "|---|---|---|---|---|---|---|---|---|---|---|"]
    tot = {k: 0 for k in order}
    rob_tot = {"co-located": 0, "single": 0}
    for name, mode in groups:
        sub = [r for r in records if (r["scope"] == name if mode != "extra" else r["file"] == name)]
        c = {k: sum(1 for r in sub if r["status"] == k) for k in order}
        rob = {k: sum(1 for r in sub if r["status"] == k and r.get("robust")) for k in rob_tot}
        for k in order:
            tot[k] += c[k]
        for k in rob_tot:
            rob_tot[k] += rob[k]
        out.append(f"| {name} | {mode} | {len(sub)} | {c['co-located']} [{rob['co-located']}] | "
                   f"{c['single']} [{rob['single']}] | {c['consistent']} | {c['derived']} | "
                   f"{c['code/design']} | {c['union']} | {c['exception']} | {c['UNEXPLAINED']} |")
    out.append(f"| **total** | | {len(records)} | {tot['co-located']} [{rob_tot['co-located']}] | "
               f"{tot['single']} [{rob_tot['single']}] | {tot['consistent']} | {tot['derived']} | "
               f"{tot['code/design']} | {tot['union']} | {tot['exception']} | {tot['UNEXPLAINED']} |")
    for status in ["UNEXPLAINED", "union", "exception", "derived", "code/design", "consistent", "single", "co-located"]:
        sub = [r for r in records if r["status"] == status]
        out += ["", f"## {status} ({len(sub)})", "",
                "| doc | line | scope | numeral | source | context |", "|---|---|---|---|---|---|"]
        for r in sub:
            src = r.get("reason") or r.get("source", "")
            if r.get("transform") and r["transform"] != "=":
                src += f" ({r['transform']})"
            if status in ("co-located", "single") and not r.get("robust"):
                src += f" [NOT decoy-robust: {r['decoys']}/4]"
            out.append(f"| {r['file']} | {r['line']} | {r['scope']} | {r['token']} | {src} | "
                       f"{r['context'].replace('|', '\\|')} |")
    (HERE / "report.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out[5:5 + len(groups) + 2]))


if __name__ == "__main__":
    main()
