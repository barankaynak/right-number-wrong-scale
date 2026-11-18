# Manuscript numeral audit

These scripts check that every numeral in the manuscript traces to a released source.
Both use the Python standard library only, read the released files, and write only into
this folder.

```
python -I derived_values.py    # recompute derived values -> derived_values.json
python -I audit_numerals.py    # audit -> report.md, report.json
```

## What is checked

The audit reads every numeral in `paper/main.tex`. It also reads the highlights, the
cover letter and the graphical abstract. Each numeral is checked at the precision it is
printed with. A numeral can match a source value directly, or as a percentage of a
fraction (×100), or the reverse (÷100).

| Status | Meaning |
|---|---|
| co-located | A results-section line, checked against that section's analysis summaries. All numerals on the line appear together in one output record: a small JSON object, or a few consecutive lines of printed output. |
| single | A results-section numeral found on its own in that section's summaries. |
| consistent | A numeral in the abstract, introduction, discussion, threats, conclusion or an extra document that equals a matched results numeral. |
| derived | Recomputed from released outputs. The values in `derived_values.json` are pooled counts, Model A+B minus A differences, per-question means and Wilson intervals; each entry names its formula and inputs. A percentage can also be the ratio of two numerals on the same line. |
| code/design | Parameters and design constants, found in the hash-frozen code or the pre-registration documents. |
| union | Found only in the union of all summaries. This is weaker evidence; the report lists each case. |
| exception | Listed in `exceptions.csv` with a reason, such as the ORCID iD or a worked example. |
| UNEXPLAINED | None of the above. The audit passes when this count is zero. |

## Decoy test

The output files are dense, so a single numeral can match one of them by chance. Each
match is therefore also tested with four decoys: the numeral shifted by ±3 and ±7 units
in its last printed digit. A match is decoy-robust when at most one decoy also matches.
The report gives the robust count separately and marks each non-robust match.

## Matcher sensitivity sources (added 2026-11-14)

The post-outcome matcher sensitivity (`prereg-v3.8`, Appendix `app:matcher`) adds
`results/sens_v225/*.json` and the `frozen` and `both` re-analyses under
`results/sens_v225/analysis/` to the G1, G1-MT, taxonomy, cross-lingual and App D scopes,
and is the only source of the App E scope. `derived_values.py` computes its shares and
sums (`matcher_sensitivity`). Block denominators there are S1's, which exclude records
flagged `fallback`, as the paper does.

## Sources not used

Raw LLM traces (`*.jsonl`) and logs are never used as audit sources. The derived-value
script is the one exception: it reads the stored G4 injection files to rebuild the GFP
reference column of the verifier table.
