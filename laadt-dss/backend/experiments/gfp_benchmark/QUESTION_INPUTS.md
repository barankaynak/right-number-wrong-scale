# Question input coverage (descriptive, not pre-registered)

Classified 2026-11-04, during human coding of A22-2/A26 and **before any October G1 outcome
was examined**. It is a description of the question set, not an analysis, and is not used by
any pre-registered test. Prompted by coder 1's question S4 (`results/oct_v42/audit/CODER_QA_LOG.md`),
which showed that the S1 answer ("every question states the inputs it needs") was wrong.

**Criterion.** A question is *under-specified* if its text (TR and EN; the two state the same
values) gives no value for an argument that one of its `expected_tools` requires in the tool
schema, and that value cannot be taken from an earlier tool's output in the same chain.
Required arguments (`app/llm/ollama_orchestrator.py` tool schemas):

| tool | required |
|---|---|
| `simulate_pv_bess`, `run_monte_carlo` | `city`, `panel_kw` |
| `simulate_grid_impact` | `pv_penetration_pct` |
| `run_policy_scenario` | `base_investment_tl`, `annual_savings_tl` (from the text, or from a preceding `simulate_pv_bess`) |

`suggested_args` (the reference-graph arguments) supply these values; a model sees only the text.

## Clear (17)

| id | missing required value |
|---|---|
| res-04 | `panel_kw` ("appropriately sized") |
| res-11 | `city`; `pv_penetration_pct` |
| res-12 | `city`; `pv_penetration_pct` |
| com-12 | `city` |
| dis-03 | `pv_penetration_pct` |
| dis-09 | `pv_penetration_pct` (200 roofs x 5 kW; feeder size not given) |
| dis-10 | `pv_penetration_pct` |
| sta-01 | `city` |
| sta-02 | `base_investment_tl`, `annual_savings_tl` |
| sta-03 | `base_investment_tl`, `annual_savings_tl` |
| sta-05 | `city` |
| sta-06 | `base_investment_tl`, `annual_savings_tl` |
| sta-07 | `city`, `panel_kw` |
| sta-08 | `base_investment_tl`, `annual_savings_tl` (40 kW stated, no PV tool in chain) |
| sta-09 | `base_investment_tl`, `annual_savings_tl` |
| sta-10 | `city` |
| sta-11 | `annual_savings_tl` (investment stated) |

## Strict reading only (4)

| id | why only on a strict reading |
|---|---|
| com-10 | PV inputs stated; the grid step's `pv_penetration_pct` is not |
| com-11 | "all facilities" could be read as 100 % penetration |
| dis-05 | penetration sweep; the starting `pv_penetration_pct` is not stated |
| dis-13 | penetration sweep; the starting `pv_penetration_pct` is not stated |

## Fully specified (35)

All other questions: res-01, res-02, res-03, res-05, res-06, res-07, res-08, res-09, res-10,
res-13, res-14, com-01 to com-09, com-13, com-14, com-15, dis-01, dis-02, dis-04, dis-06, dis-07,
dis-08, dis-11, dis-12, dis-14, sta-04, sta-12, sta-13.

Single classifier (Claude, at the author's request); the criterion is mechanical except for
the four strict-reading cases, which are listed separately for that reason.

# Reference reachability (added 2026-11-05, also before any October outcome)

A different question: can a faithful model reach the **reference graph's** numbers from the
text alone? This affects every G1 reference score, not only G1-MT. Declared in
PREREGISTRATION.md (Beyan, 2026-11-05).

**Criterion.** A question is *not fully reachable* if at least one reference argument value
(any step of `suggested_args[_per_step]`; excluding `stakeholder_type`, `$prev.*` and boolean
flags) is neither stated in the text nor equal to the tool default. Tool defaults
(`app/llm/ollama_orchestrator.py`): `city` ankara; `bess_kwh` 0; `bess_chemistry` LFP;
`lifetime_years` 25; `discount_rate` 0.12; `bess_penetration_pct` 0; annual consumption 5000 kWh
when neither consumption nor bill is given.

Method: an automatic scan (number and city matching in TR+EN text) plus a manual pass. The
manual pass corrected three false "stated" matches where another number in the text equals the
argument value: res-11 and com-10 (`pv_penetration_pct` 40 vs "40 flats" / "40 kW") and sta-01
(`bess_kwh` 10 vs "10 kW").

## Not fully reachable (25)

| id | unstated non-default reference values |
|---|---|
| res-04 | panel_kw 4 |
| res-08 | annual_consumption_kwh 4200 |
| res-10 | bess_kwh 8 |
| res-11 | city istanbul; pv_penetration_pct 40 |
| res-12 | city izmir; pv_penetration_pct 40 |
| com-05 | annual_consumption_kwh 70000 |
| com-10 | pv_penetration_pct 40 (step 2) |
| com-11 | pv_penetration_pct 80 |
| com-14 | bess_kwh 30 |
| dis-03 | pv_penetration_pct 30 |
| dis-05 | pv_penetration_pct 50 |
| dis-09 | pv_penetration_pct 45 |
| dis-10 | pv_penetration_pct 80 |
| dis-13 | pv_penetration_pct 10 |
| sta-01 | bess_kwh 10; monthly_bill_tl 2500 |
| sta-02 | base_investment_tl 400000; annual_savings_tl 55000; discount_rate 0.15 |
| sta-03 | base_investment_tl 350000; annual_savings_tl 48000; lifetime_years 20; discount_rate 0.14 |
| sta-05 | city istanbul; monthly_bill_tl 18000 |
| sta-06 | base_investment_tl 300000; annual_savings_tl 42000; lifetime_years 20 |
| sta-07 | city bursa; panel_kw 30; bess_kwh 15; annual_consumption_kwh 60000; pv_penetration_pct 40 |
| sta-08 | base_investment_tl 900000; annual_savings_tl 110000 |
| sta-09 | base_investment_tl 250000; annual_savings_tl 35000; lifetime_years 20; discount_rate 0.15 |
| sta-10 | city konya; bess_kwh 5; monthly_bill_tl 1800; pv_penetration_pct 40 |
| sta-11 | annual_savings_tl 28000; lifetime_years 15; discount_rate 0.15 |
| sta-12 | bess_kwh 10; monthly_bill_tl 9000 |

com-12 is under-specified by the schema criterion above (no city), but its reference uses the
default city, so it is reachable.

**A27-1's eight policy questions.** com-13, sta-04 and sta-08 state the discount rate and the
lifetime in the text. sta-06 states the discount rate but not the lifetime. sta-02, sta-03,
sta-09 and sta-11 state neither. The A27-1 schema fix therefore makes the reference fully
reachable only for com-13 and sta-04. sta-08 stays unreachable for a different reason: its
investment and savings amounts are not stated. Six of the eight are therefore in the list of 25.

## Output not produced by the tool path: transformer deferral

`_run_grid_impact` (`app/llm/ollama_orchestrator.py`) sends only `pv_penetration_pct`,
`bess_penetration_pct` and `run_penetration_sweep`. It never sets `run_deferral_analysis`,
which the `/simulate/grid-impact` route needs before it returns `transformer_deferral`. As a
result, no reference graph and no session graph can contain a deferral record.

Four questions ask for deferral:
- dis-05 and dis-11 ask for nothing else, so no traceable answer exists in any arm.
- dis-08 and res-12 also ask for other quantities.

## Sensitivity subset (30)

These are the questions with neither limit: 56 − 25 not fully reachable − dis-11.
