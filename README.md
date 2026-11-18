# Right Number, Wrong Scale — code, data and traces

This archive accompanies the article *Right Number, Wrong Scale: Measuring Grounding Fidelity in
LLM-Orchestrated Energy-Investment Decision Support from Buildings to Feeders* (B. Kaynak, Sakarya
University; ORCID 0000-0002-9004-2639). It holds the frozen code the study evaluated, the
pre-registration, the benchmark, the analysis scripts, and the raw traces and results behind the
article's tables and figures.

The platform itself (LAaDT-DSS) is maintained separately at
https://github.com/barankaynak/laadt-dss. That repository holds a **later** state of the code. Its
server chat runs a corrected orchestrator by default; `LLM_ORCHESTRATOR=frozen` restores the
orchestrator and guard evaluated here. To reproduce this study, use **this** archive.

## Layout

| Path | Content |
|---|---|
| `laadt-dss/backend/app/` | Frozen platform code as evaluated: simulators, the LLM orchestrator and the provenance guard (`app/llm/provenance_guard.py`, SHA-256 `a050b46a…`). |
| `laadt-dss/backend/tests/` | The platform's test suite at the frozen commit. |
| `laadt-dss/backend/experiments/gfp_benchmark/` | Pre-registration (`PREREGISTRATION.md`, `PREREGISTRATION_G3.md`), codebooks, question set, run harnesses, analysis scripts, figures. |
| `…/gfp_benchmark/results/` | Raw traces and computed results of every reported run (G1, G1-MT, G2, G3, G4, cross-lingual, cross-model, the remote-model check), including the human coding sheets and the commercial verifier's inputs and outputs. |
| `…/gfp_benchmark/manuscript_audit/` | The script that matches every numeral of the article to its source, and its report. |
| `PREREG_TAGS.md` | The pre-registration tags (`prereg-v1.0` … `prereg-v3.8`) cited in the article, with their commits and dates. |
| `RELEASE_NOTE.md` | The files changed for the public release, with their original SHA-256, and what was left out. |

## Result → article map

| Result | Article | Supplementary Material |
|---|---|---|
| G3 cross-scale critical factors | Sec. 5.1, Table 2, Fig. 4 | S4 |
| G4 detection under error injection | Sec. 5.2, Table 3, Fig. 5 | S5 |
| G1 live fail-closed guard | Sec. 5.3, Table 4, Fig. 6 | S6 |
| G1-MT second turn | Sec. 5.4 | S7 |
| Live-flag taxonomy (exploratory) | Sec. 5.5 | S8 |
| G2 chain length | Sec. 5.6 | — |
| Cross-lingual and cross-model | Sec. 5.7, Table 5 | S10 |
| Tolerance sweep | — | S9 |
| Parameters | — | S2 |
| Matcher sensitivity (post-outcome) | Appendix B | — |

## Running

All code runs in Docker (Python 3, `numpy<2.0`, `demandlib==0.1.9`; see `requirements.txt`).

```bash
cd laadt-dss
docker-compose up -d db redis backend
docker-compose --profile test run --rm test pytest tests/ -q
```

The live runs used local open-weight models served by Ollama. Set `OLLAMA_HOST` to your server. The
remote-model check used an OpenAI-compatible hosted endpoint: set `EVREN_BASE_URL` and
`EVREN_API_KEY`. The commercial verifier (Jev 1.13) needs its own key. Its recorded inputs and
outputs are in `results/` so that the comparison can be re-checked without it.

Most analyses read the recorded traces and need no model server. Each script names its inputs and
outputs at the top.

## Checking the frozen state

`PREREGISTRATION.md` lists the SHA-256 (LF line endings) of every frozen file at each tag. Compare
with `sha256sum <file>` here. A file changed by a later frozen version matches its later row. The
files changed for release are listed with their original hashes in `RELEASE_NOTE.md`.

## Licence

Code: MIT (`LICENSE`). Data, traces and documentation: CC BY 4.0.

## Citation

See `CITATION.cff`.
