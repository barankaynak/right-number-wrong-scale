# oct_v42_evren — A30 exploratory run (EVREN, deepseek-v4.1-flash, Turkish)

Pre-registered as A30 under `prereg-v3.6` (see `../../PREREGISTRATION.md`). Exploratory and
descriptive only.

- **Authoritative files:** the copies committed in `d159c16` (analysis outputs) together with the
  raw files in this folder: `raw_g1_deepseek-v4.1-flash_20261106T091533Z.jsonl` (504 rows),
  `raw_mt_deepseek-v4.1-flash_20261107T044521Z.jsonl` (189 rows),
  `determinism_check_deepseek-v4.1-flash_20261107T044203Z.jsonl` (5 rows), `a30_calls.jsonl`,
  `a30_log.jsonl`, `run.log`.
- **`aborted_*`:** the first G1 attempt, cut by a host shutdown at 291 of 504 rows on 2026-11-06.
  Archived unanalysed; the re-run was declared before it started (Beyan in commit `f339c41`).
- **`_seafile_conflicts/`:** five `(SFConflict …)` copies created by the Seafile sync client on
  2026-11-08, after the run ended. Four are byte-identical to the main files; one is an older
  526-line prefix of `a30_calls.jsonl`. Kept for the record, never analysed (Beyan 2026-11-10).
- **Analysis:** `GFP_RUN_DIR=oct_v42_evren python -m experiments.gfp_benchmark.a30_analysis`
  (stdout in `analysis/a30_analysis.out`). The paper reports the pre-selected quantities in the
  appendix "Exploratory check on one remote model".
