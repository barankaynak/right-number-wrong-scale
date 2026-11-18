"""Mahsuplaşma (net metering) netleme-aralığı motoru testleri (A7).

TR rejimi: mesken=aylık, ticarethane=saatlik netleme. Aylık netleme öğle-fazlasını
akşam-tüketimine perakendede mahsup eder → PV lehine (savings ↑).
"""
import numpy as np
import pytest

from app.simulation.economic.economic_engine import (
    apply_netting, _period_ids, simulate_annual_cashflow,
)
from app.simulation.loads.turkey_parameters import (
    netting_interval_for, NETTING_INTERVAL_BY_STAKEHOLDER,
)


def _noon_export_evening_import(kwh=5.0):
    """Her gün öğle kwh export, akşam kwh import (aynı gün, farklı saat)."""
    imp = np.zeros(8760)
    exp = np.zeros(8760)
    imp[18::24] = kwh          # akşam import
    exp[12::24] = kwh          # öğle export
    return imp, exp


def test_period_ids_monthly_has_12_groups():
    ids = _period_ids(8760, "monthly")
    assert len(np.unique(ids)) == 12
    assert ids[0] == 0 and ids[-1] == 11
    # Ocak = 31×24 = 744 saat
    assert (ids == 0).sum() == 744


def test_period_ids_daily_and_annual():
    assert len(np.unique(_period_ids(8760, "daily"))) == 365
    assert len(np.unique(_period_ids(8760, "annual"))) == 1
    assert len(np.unique(_period_ids(8760, "hourly"))) == 8760


def test_hourly_netting_no_offset_across_hours():
    """Saatlik netleme farklı saatleri mahsup ETMEZ (öğle export ≠ akşam import saati)."""
    imp, exp = _noon_export_evening_import(5.0)
    bi, be = apply_netting(imp, exp, "hourly")
    assert bi == pytest.approx(imp.sum())      # tüm import faturalanır
    assert be == pytest.approx(exp.sum())      # tüm export satılır


def test_monthly_netting_offsets_same_month():
    """Aylık netleme aynı-ay öğle-fazlasını akşam-tüketimine mahsup eder → net 0."""
    imp, exp = _noon_export_evening_import(5.0)   # her gün dengeli
    bi, be = apply_netting(imp, exp, "monthly")
    assert bi == pytest.approx(0.0, abs=1e-6)
    assert be == pytest.approx(0.0, abs=1e-6)


def test_monthly_surplus_only_net_exported():
    """Öğle 10, akşam 4 → aylık net-fazla (6/gün) ihraç; import 0."""
    imp = np.zeros(8760); exp = np.zeros(8760)
    imp[18::24] = 4
    exp[12::24] = 10
    bi, be = apply_netting(imp, exp, "monthly")
    assert bi == pytest.approx(0.0, abs=1e-6)
    assert be == pytest.approx((10 - 4) * 365, rel=1e-6)   # yalnız net fazla


def test_monthly_savings_ge_hourly_for_pv():
    """PV (öğle-export/akşam-import) için aylık netleme saatlikten AZ OLMAYAN tasarruf."""
    imp, exp = _noon_export_evening_import(5.0)
    bess = {"grid_import_kwh": imp, "grid_export_kwh": exp, "self_consumption_ratio": 0.5}
    tariff = {"day_rate_tl_per_kwh": 2.0, "export_rate_tl_per_kwh": 0.5, "vat_rate": 0.1}
    load = np.full(8760, 5.0)
    h = simulate_annual_cashflow(np.zeros(8760), bess, load, tariff, netting_interval="hourly")
    m = simulate_annual_cashflow(np.zeros(8760), bess, load, tariff, netting_interval="monthly")
    assert m["annual_savings_tl"] >= h["annual_savings_tl"]
    assert m["netting_offset_kwh"] > h["netting_offset_kwh"]  # aylık daha çok mahsup
    assert h["netting_interval"] == "hourly" and m["netting_interval"] == "monthly"


def test_stakeholder_mapping():
    assert netting_interval_for("residential") == "monthly"
    assert netting_interval_for("commercial") == "hourly"
    assert netting_interval_for("municipal") == "hourly"
    assert netting_interval_for("utility") == "hourly"
    assert netting_interval_for("RESIDENTIAL") == "monthly"     # büyük-küçük harf
    assert netting_interval_for("bilinmeyen") == "hourly"       # varsayılan
    assert netting_interval_for(None) == "hourly"


def test_default_backward_compatible_hourly():
    """netting_interval verilmezse 'hourly' (mevcut davranış korunur)."""
    imp, exp = _noon_export_evening_import(3.0)
    bess = {"grid_import_kwh": imp, "grid_export_kwh": exp}
    tariff = {"day_rate_tl_per_kwh": 2.0, "export_rate_tl_per_kwh": 0.5, "vat_rate": 0.1}
    cf = simulate_annual_cashflow(np.zeros(8760), bess, np.full(8760, 3.0), tariff)
    assert cf["netting_interval"] == "hourly"
    assert cf["billed_import_kwh"] == pytest.approx(imp.sum())


def test_conservation_billed_le_physical():
    """Faturalanan miktarlar fiziksel toplamı AŞMAZ (mahsup yalnız azaltır)."""
    imp, exp = _noon_export_evening_import(7.0)
    for iv in ("hourly", "daily", "monthly", "annual"):
        bi, be = apply_netting(imp, exp, iv)
        assert bi <= imp.sum() + 1e-9
        assert be <= exp.sum() + 1e-9
        # mahsup edilen import = mahsup edilen export (enerji korunumu)
        assert (imp.sum() - bi) == pytest.approx(exp.sum() - be, abs=1e-6)
