# v2.25 matcher sensitivity: results (2026-11-14)

- Pre-registered at `prereg-v3.8` (46db805). Script: `sens_v225.py` (sha 47c30854…, recorded in `gate.json`).
- Variants: `frozen`, `sign` (the shared `claim_sign` rule), `decimal` and `both`.
- No LLM calls. The guard's live decisions are unchanged; only the stored texts are re-scored.
- Primary results stay those of the frozen matcher.

## S0: gate

- The frozen matcher reproduced every stored count exactly: 14 files, all three stages, 0 losses, no trace dropped.
- The S3 outputs of the frozen copy are byte-identical to the paper's outputs (frozen-only dry run, `../sens_v225_dryrun/`).

## Threshold (Beyan 2026-11-14 / SCIENTIFIC_REVIEW v2.25)

| | criterion | result |
|---|---|---|
| (i) | a pre-registered test changes significance after Holm, or direction | **No for every test the threshold names; borderline for one auxiliary test.** H_G1a and H_G1b were checked in all six conditions and in A30. The pooled Holm results, the E1 bounds (sign of both bounds) and H_MT1/H_MT2 (G1-MT and A30) were checked too. G2 Kruskal–Wallis stays non-significant everywhere. **But** `H_G1a_aux` (tool lift: grounded no-guard vs ungrounded, a member of the pre-registered Holm family) turns significant for Muse under `decimal` (Holm p .234→.030; bootstrap CI still includes 0, [−0.012, +0.131]). For Mistral, Holm p .214→.091, still not significant. The direction strengthens the paper's claim. |
| (ii) | McNemar "no-guard only clean" cell leaves 0 | **No.** The primary H_G1b McNemar is x/0 in every condition and variant. |
| (iii) | Model C (Mistral) decomposed gain changes sign | **No.** It stays negative: −0.006 frozen, −0.011 sign, −0.008 decimal, −0.013 both. |
| (iv) | S4 lower bound > 10% of blocks in any condition | **Yes, from the decimal rule.** See the details below. |

S4 lower bound: blocked responses whose first draft passes under the variant, as a share of all blocks.

| condition | sign | decimal | both |
|---|---|---|---|
| G1, Muse (E) | 0.8% | 10.2% | 10.9% |
| G1, Mistral (C) | 1.1% | 6.8% | 8.0% |
| G1, other four conditions | 0% | ≤ 2.8% | ≤ 2.8% |
| G1-MT turn 2, Mistral | 0% | 12.1% (4/33) | 12.1% (4/33) |
| G1-MT turn 2, A-en | 0% | 10.3% | 10.3% |
| G1-MT turn 2, Muse | 0% | 8.2% | 10.2% |
| G1-MT turn 2, other conditions | 0% | 4.3–8.3% | 4.3–8.3% |
| A30 (EVREN) G1 | 0% | 8.5% | 8.5% |
| A30 G1-MT turn 2 | 0% | **35.4%** | **35.4%** |

- This is a lower bound, because the retry text of blocked turns is not stored. "Passes" means traceable under the variant, not correct.
- Every local exceedance is within one response of the threshold (E 13/128, A-en 4/39, C 4/33). Pooled: G1 28/788 = 3.6%; G1-MT turn 2 22/265 = 8.3%. Only A30 turn 2 (17/48) exceeds it clearly.
- Reconciliation (2026-11-14): the script's S4 counted one Mistral G1-MT record flagged `fallback` (blocked turn 2, no long-decimal or signed numeral in its draft). S1 and the paper exclude such records, so Mistral turn 2 is 4/33 (the raw `s4_block_attribution.json` shows 4/34). No other unit differs between S1 and S4.
- The sign rule alone moves at most 1 block per condition.

## Other changes worth reporting

- **Direction.** The decimal defect mostly hits the no-guard arm.
  - Delivered units whose verdict counts change under `decimal` (`s2_incidence.json`, `delivered_ref`; IGNORED-only changes included). Pooled per run (G1, G1-MT, A30): no-guard 18.9–28.4%, guard 2.3–3.5%, ungrounded ≤ 0.3%; under `both`, no-guard 19.6–32.9%. Per G1 condition: no-guard 4.8–25.3%, guard 1.3–7.7%. (The earlier "19–33%" was the per-run `both` range.)
  - The reason: long-decimal numerals (pu voltages, also small MW values) are frequent in no-guard drafts (808 in oct_v42) and rare in delivered guard text (47).
  - The H_G1b gain moves in both directions under `both`: A-tr 0, A-en −.009, B-tr +.008, B-en +.002, C −.015, E −.007, A30 +.005. No single direction, so the frozen matcher is neither "conservative" nor "favourable" toward the guard; neither word is used. The upper E1 bound falls (e.g. E +0.265→+0.238).
  - **Over-blocking** changes under `decimal`: C 4→6 and E 8→10 questions.
  - In the taxonomy, the decimal residue sits in the small-integer class, not in "unresolved": pooled flags 885→758, small-int 273→160, unresolved 410→396.
- **Sign.** Few signed numerals are involved: oct_v42 delivered guard 23, no-guard 172, ungrounded 48. They change 1–5% of units.
  - All 24 delivered summaries that failed their own check pass under `sign`: G1 18, G1-MT 2 (A-en com-12, E res-11), A30 G1 3, A30 G1-MT 1.
  - Mistral P2 gap: the sign rule widens it (P2 Δ −0.101→−0.132; 20/29 summaries with reference-GFS < 1, unchanged). The sign defect does not explain the gap.
- **Cross-lingual manipulation check** (`crosslingual_stats`, section 2) is the same comparison as `H_G1a_aux` above, with raw p: Mistral .071→.030, Muse .238→.030 under `decimal`. After Holm, only Muse is significant (see (i)).
- **S1 (P3 split).** In the "records present but empty summary" cell, the last call is mostly `simulate_grid_impact` (nested result), then `run_monte_carlo` and `run_policy_scenario` (nested, or a failed call). In G1-MT turn 2, Model B (TR and EN) and A30 have 11–13 units each with no call that turn.
- **S5 (fail-open).** 3 minus-prefixed claims were GROUNDED against positive records. None is a demonstrated sign inversion: two (Mistral res-06) are the summary's own correct NPV line ("-4,676 TL"), matched for the wrong reason to the buy-price record (4.857); the third (A30, delivered) is a VaR magnitude whose sign is ambiguous. No position fallbacks.
- **S6 (A22 audit).**
  - 6 numerals are signed: 2 GROUNDED and traceable; 1 UNGROUNDED but coded traceable (A026, a correctly quoted negative NPV: the sign defect, seen by a human); 3 UNGROUNDED and not traceable.
  - A026 is the paper's single traceable numeral among the 37 flagged against the reference graph: it is the only UNGROUNDED, coder-traceable numeral in S6, and the paper reports exactly one.
  - A025 (Muse "-139,655") is GROUNDED against the reference graph but its summary fails against the in-run graph; the cause was not checked.
  - No numerals are long-decimal at the audit markers.
- **S7 (G4 corpus).**
  - No minus-prefixed numerals, so G4 says nothing about sign inversion.
  - Long-decimal numerals: EN set 22, Mistral set 15, A set 1 (source = mutated counts). G4 detection results were not re-run, as G4 is outside the threshold.

## Files

| stage | files |
|---|---|
| S0 | `gate.json` |
| S1 | `s1_p3_split.json` |
| S2 | `s2_incidence.json` |
| S4 | `s4_block_attribution.json` |
| S5 | `s5_fail_open.json` |
| S6 | `s6_audit.json` |
| S7 | `s7_g4_corpus.json` |
| S3 | `analysis/<variant>/*.out` and `analysis/<variant>/<run>/*.json` |

Work copies (re-scored traces) were deleted after the run; they are reproducible with the commands in the script docstring.
