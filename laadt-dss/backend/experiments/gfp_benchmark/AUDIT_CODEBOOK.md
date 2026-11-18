# A22-2 — Human traceability audit: codebook (FROZEN before sampling)

Purpose: an independent, human check on whether numbers delivered to the user can be
traced to the simulator output. It bounds the "same matcher measures and intervenes"
circularity. It is **not** a correctness, category, or scale judgement (lessons of A8 and
B4: such judgements did not code reliably).

## What each coding item contains

1. The user's question (Turkish or English).
2. **Reference output sheet**: every numeric field the question's reference tool chain
   produced, one row per field: field name, value, unit, and the value printed in both
   Turkish (`219.000,5`) and English (`219,000.5`) number formats.
3. The **delivered response** exactly as the user received it, with every number the
   parser found marked and numbered `[#1]`, `[#2]`, … in place.

Coders never see the experimental arm, the intervention path, or any matcher verdict.
Note: deterministic provenance summaries begin with a fixed template header, so coders
can tell that an item is a summary; blinding is to the matcher's verdicts, not to this.

## Variables

### `traceable_YN` — one per numbered number

Question: *Does this number appear on the reference output sheet, allowing for
rounding?*

- **Y** if a sheet value equals it after rounding to the precision the response uses
  (e.g. `219.000` or `219 bin` vs `219000.0`; `%53,8` vs `0.538`; `7,3 MWh` vs
  `7300 kWh`). Unit conversions that are pure rescaling (kWh↔MWh, ratio↔percent,
  thousand/million words) count as the same value.
- **Y** if the number restates an input the question itself gave (e.g. "5 kW" when
  the question says 5 kW). Mark it Y and tick `input_echo`.
- **N** if no sheet value or question input matches it after rounding.
- **N/A** for numbers that state no quantity: list numbering ("1.", "2)"), dates and
  years, step labels ("Aşama 2"), counts of items in the answer itself.

Do **not** judge whether the number is used at the right scale, for the right
quantity, or whether it is correct; only whether it can be found.

Ties and doubt: if you would need more than simple rounding or a pure unit rescaling to
make it match, code **N**.

### `usable_answer_YN` — one per response

Question: *Does the delivered text answer the question's numerical request with at
least one number?* (e.g. a payback question gets a payback figure).

- **Y**: at least one number addresses what was asked.
- **N**: the text gives no number for what was asked (e.g. asks for inputs, says no
  simulation was run, or lists unrelated fields only).

## Procedure

- Two coders. Coder 1 is an author (declared). Coder 2 is blind to coder 1's labels.
- Each coder works alone on the same item set, in the randomised order provided.
- No discussion until both sheets are submitted and hashed.
- If inter-coder agreement is low, the A18 rule applies unchanged: raw κ, strict/lenient
  bounds, then a consensus pass in which a code may change only with a cited codebook
  clause. No re-coding and no codebook revision after coding starts.

## Pre-registered analyses (A22-2)

- Cohen's κ at number level (`traceable_YN`, N/A excluded) and at response level
  (`usable_answer_YN`).
- **Y1** = share of human-traceable numbers among numbers the reference matcher marked
  GROUNDED, per intervention path, with Wilson 95% CI. This is the circularity bound
  reported in the paper.
- **Y2** = share of human-traceable numbers among numbers the matcher marked as a
  violation (matcher false positives in delivered text).
- Usable-answer rate per path.
- Descriptive; reported regardless of outcome; cannot be dropped later.
