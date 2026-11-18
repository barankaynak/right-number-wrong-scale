# ABORTED — G1 re-run under prereg-v3.0 (A21), stopped 2026-10-14 16:01 UTC

Reason (A23): PV irradiance fault found during internal review — pvlib 0.15.2's
`get_pvgis_tmy` returns 2 values, `solar_model.py` unpacked 4, the bare `except`
silently fell back to clear-sky irradiance (no provenance flag). All PV tool outputs in
this run (and in the July run) were clear-sky. Scientific advisor v2.22.8: stop, fix,
re-freeze (A22+A23, prereg-v3.1), restart all 5 conditions x 3 arms.

These traces were NOT analysed (A21-E5 no-interim-look; A23-1: results not viewed).
Only trace counts / error / environment fields were checked while running.
Archived for completeness; not used in any reported result.
