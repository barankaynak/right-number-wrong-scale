import pytest
import numpy as np
from app.simulation.economic.economic_engine import (
    calculate_npv,
    calculate_irr,
    calculate_payback_period,
    calculate_lcoe,
    simulate_annual_cashflow,
)
from app.simulation.economic.tariffs.turkey_2026 import get_simple_tariff, calculate_tiered_bill


def test_npv_calculation():
    # Manual: -100 + 60/(1.1) + 60/(1.1^2) = -100 + 54.545 + 49.587 = 4.13
    cash_flows = [-100, 60, 60]
    npv = calculate_npv(cash_flows, 0.10)
    assert abs(npv - 4.132) < 0.01


def test_irr_calculation():
    # IRR of [-100, 60, 60] is ~13.07%
    cash_flows = [-100, 60, 60]
    irr = calculate_irr(cash_flows)
    assert abs(irr - 0.1306) < 0.001


def test_payback_period():
    # -100 + 40 + 40 + 40 -> breaks even at year 3 (simple)
    cash_flows = [-100, 40, 40, 40]
    result = calculate_payback_period(cash_flows, discount_rate=0.0)
    assert result["simple"] == 3.0


def test_tiered_bill():
    # Kendi-tutarlı beklenti: dilimli (marjinal) kademe, RESIDENTIAL_TIERS'tan hesaplanır
    # (sabit değer hardcode edilmez — resmî tarife güncellenince test kırılmasın,
    #  mekanik yine doğrulansın). Yapı: A0 ground-truth, bkz. turkey_2026.py kaynakları.
    from app.simulation.economic.tariffs.turkey_2026 import RESIDENTIAL_TIERS, VAT_RATE
    threshold = RESIDENTIAL_TIERS[0]["limit_kwh"]          # 240 kWh (30 gün × 8 kWh/gün)
    r1 = RESIDENTIAL_TIERS[0]["rate_tl_per_kwh"]
    r2 = RESIDENTIAL_TIERS[1]["rate_tl_per_kwh"]
    kwh = 500.0
    expected = (threshold * r1 + (kwh - threshold) * r2) * (1 + VAT_RATE)
    bill = calculate_tiered_bill(kwh)
    assert abs(bill - expected) < 0.01
    # Dilimli yapı: eşik altı tüketim tamamen düşük kademeden faturalanır
    low = calculate_tiered_bill(threshold)
    assert abs(low - threshold * r1 * (1 + VAT_RATE)) < 0.01


def test_tariff_ground_truth_invariants():
    """A0: tarife modülü yapı-invaryantları (yayınlanan resmî değerlerle uyum)."""
    from app.simulation.economic.tariffs import turkey_2026 as t
    # Vergi modeli (BTV %5 aktif-enerjiye, KDV %10 topluma) yayınlanan vergili
    # kademe fiyatlarını (3,24 / 4,86 TL/kWh, 4 Nisan 2026) ±0,01 ile üretmeli
    t1 = t._incl_tax_residential(t.RESIDENTIAL_ACTIVE_ENERGY_TL["tier1"], t.DISTRIBUTION_TL_PER_KWH)
    t2 = t._incl_tax_residential(t.RESIDENTIAL_ACTIVE_ENERGY_TL["tier2"], t.DISTRIBUTION_TL_PER_KWH)
    assert abs(t1 - t.RESIDENTIAL_INCL_TAX_TL["tier1"]) < 0.01
    assert abs(t2 - t.RESIDENTIAL_INCL_TAX_TL["tier2"]) < 0.01
    # Kademe eşiği günlük-ortalama esaslı: 30 gün → 240 kWh
    assert t.RESIDENTIAL_TIERS[0]["limit_kwh"] == t.RESIDENTIAL_DAILY_THRESHOLD_KWH * 30
    # Kademeler artan fiyatlı, üst kademe sınırsız
    assert t.RESIDENTIAL_TIERS[0]["rate_tl_per_kwh"] < t.RESIDENTIAL_TIERS[1]["rate_tl_per_kwh"]
    assert t.RESIDENTIAL_TIERS[-1]["limit_kwh"] == float("inf")
    # Mahsuplaşma: export bedeli = yalnız aktif enerji (5346 Md.6/A) → perakende fiyatın ALTINDA
    tariff = t.get_simple_tariff()
    assert tariff["export_rate_tl_per_kwh"] < tariff["day_rate_tl_per_kwh"]
    assert tariff["export_rate_tl_per_kwh"] == t.RESIDENTIAL_ACTIVE_ENERGY_TL["tier1"]
    # TOU pencereleri 24 saati kapsar, puant en pahalı, gece en ucuz
    rates = [t.tou_rate_for_hour(h, include_vat=False) for h in range(24)]
    assert all(r > 0 for r in rates)
    assert max(rates) == t.TOU_WINDOWS["peak"]["rate_tl_per_kwh_ex_vat"]
    assert min(rates) == t.TOU_WINDOWS["night"]["rate_tl_per_kwh_ex_vat"]
    # Kaldırılmış kalemler koda geri sızmasın (TRT payı / Enerji Fonu — 7346 s. Kanun)
    src = open(t.__file__, encoding="utf-8").read()
    assert "TRT_PAYI_RATE" not in src and "ENERJI_FONU_RATE" not in src


def test_tiered_bill_inversion_roundtrip():
    """sizing.invert_tiered_bill, calculate_tiered_bill'in kesin tersi kalmalı (A0 sonrası)."""
    from app.simulation.advisor.sizing import invert_tiered_bill
    for kwh in [0.0, 100.0, 239.9, 240.0, 240.1, 300.0, 500.0, 1200.0]:
        bill = calculate_tiered_bill(kwh)
        recovered = invert_tiered_bill(bill)
        assert abs(recovered - kwh) < 0.5, f"{kwh} kWh → {bill:.2f} TL → {recovered:.3f} kWh"


def test_annual_cashflow():
    pv_profile = np.array([5.0, 0.0] * 4380)  # 8760 hours, alternating
    load_profile = np.array([3.0] * 8760)      # constant 3 kW load

    from app.simulation.bess.battery_model import BatteryModel
    battery = BatteryModel(capacity_kwh=14.4)
    bess_result = battery.dispatch_self_consumption(pv_profile, load_profile)

    tariff = get_simple_tariff()
    result = simulate_annual_cashflow(pv_profile, bess_result, load_profile, tariff)

    # Should have positive savings
    assert result['annual_savings_tl'] > 0
    assert result['total_production_kwh'] > 0
    assert 0 <= result['self_consumption_ratio'] <= 1.0
