"""A27 — tool-path audit fixes (prereg-v3.3).

Each production fix is paired with a check that the July 2026 replay
(`IRRADIANCE_SOURCE=clearsky`) keeps the old behaviour, so the archived corpus
replays byte-identically.
"""
import json
from pathlib import Path

import numpy as np
import pytest

from app.llm.ollama_orchestrator import SIMULATION_TOOLS
from app.simulation.economic.economic_engine import simulate_annual_cashflow
from app.simulation.economic.tariffs.turkey_2026 import get_simple_tariff
from app.simulation.policy.policy_engine import apply_incentive
from app.simulation.pv.solar_model import simulate_pv_production

QUESTIONS = Path(__file__).resolve().parents[1] / "experiments" / "gfp_benchmark" / "questions.json"


def _schema(name: str) -> set:
    for t in SIMULATION_TOOLS:
        if t["function"]["name"] == name:
            return set(t["function"]["parameters"].get("properties", {}))
    raise KeyError(name)


def test_policy_schema_exposes_discount_rate_and_lifetime():
    assert {"discount_rate", "lifetime_years"} <= _schema("run_policy_scenario")


def test_every_reference_argument_is_in_the_tool_schema():
    """The reference graph may only use arguments the model can also send."""
    questions = json.loads(QUESTIONS.read_text(encoding="utf-8"))["questions"]
    missing = []
    for q in questions:
        per_step = q.get("suggested_args_per_step") or [q.get("suggested_args") or {}]
        for i, tool in enumerate(q.get("expected_tools", [])):
            args = per_step[i] if i < len(per_step) else {}
            extra = set(args or {}) - _schema(tool) - {"stakeholder_type"}
            if extra:
                missing.append((q["id"], tool, sorted(extra)))
    assert missing == []


def _cashflow(monkeypatch, source: str) -> dict:
    monkeypatch.setenv("IRRADIANCE_SOURCE", source)
    load = np.full(8760, 0.5)
    bess = {"grid_import_kwh": load.copy(), "grid_export_kwh": np.zeros(8760)}
    return simulate_annual_cashflow(np.zeros(8760), bess, load, get_simple_tariff())


def test_vat_is_not_added_to_a_vat_inclusive_price(monkeypatch):
    tariff = get_simple_tariff()
    out = _cashflow(monkeypatch, "pvgis_tmy_cache")
    assert out["cost_without_solar_tl"] == pytest.approx(4380 * tariff["day_rate_tl_per_kwh"], rel=1e-6)


def test_july_replay_keeps_the_old_double_vat(monkeypatch):
    tariff = get_simple_tariff()
    out = _cashflow(monkeypatch, "clearsky")
    expected = 4380 * tariff["day_rate_tl_per_kwh"] * (1 + tariff["vat_rate"])
    assert out["cost_without_solar_tl"] == pytest.approx(expected, rel=1e-6)


def _peak_hour(monkeypatch, source: str) -> int:
    monkeypatch.setenv("IRRADIANCE_SOURCE", source)
    pv = simulate_pv_production(39.93, 32.86, 5.0, 30.0, 180.0)
    return int(pv.reshape(365, 24).mean(axis=0).argmax())


def test_pv_profile_is_in_local_time(monkeypatch):
    """Ankara solar noon is ~12:50 local (UTC+3), ~09:50 UTC."""
    assert 11 <= _peak_hour(monkeypatch, "pvgis_tmy_cache") <= 13


def test_july_replay_keeps_the_utc_pv_profile(monkeypatch):
    assert 9 <= _peak_hour(monkeypatch, "clearsky") <= 10


def test_tax_deduction_default_rate_is_a_fraction():
    cf = apply_incentive([-100_000.0, 10_000.0], {"type": "tax_deduction"})
    assert cf[0] == pytest.approx(-100_000.0 + 100_000.0 * 1.0 * 0.25)
