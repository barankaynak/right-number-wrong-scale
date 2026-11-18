"""
Ortak PV+BESS fizibilite servisi.

`run_pv_bess(req)` — hem `/api/v1/simulate/pv-bess` route'u hem de
`/api/v1/advisor/recommend` aynı deterministik mantığı çağırsın diye
`api/routes/simulation.py` içindeki gövde buraya çıkarıldı (drift önlenir).

`req` herhangi bir attribute-erişimli nesne olabilir (Pydantic modeli veya
`types.SimpleNamespace`). Beklenen alanlar (opsiyoneller None olabilir):
    latitude, longitude, panel_kw, tilt, azimuth,
    bess_kwh, bess_chemistry, annual_consumption_kwh, stakeholder_type,
    discount_rate, system_cost_tl, lifetime_years,
    electricity_buy_price_tl_per_kwh, electricity_sell_price_tl_per_kwh,
    pv_capex_per_kwp, battery_capex_per_kwh
"""

import numpy as np

from app.simulation.pv.solar_model import irradiance_provenance, simulate_pv_production
from app.simulation.pv.load_profile import generate_load_profile
from app.simulation.bess.battery_model import BatteryModel
from app.simulation.economic.economic_engine import (
    calculate_npv, calculate_irr, calculate_payback_period,
    calculate_lcoe, simulate_annual_cashflow,
)
from app.simulation.economic.tariffs.turkey_2026 import get_simple_tariff

# Birim CAPEX varsayılanları (TL) — sistem maliyeti verilmediğinde kullanılır
DEFAULT_PV_CAPEX_PER_KWP = 25000.0
DEFAULT_BESS_CAPEX_PER_KWH = 20000.0
TARIFF_GROWTH_RATE = 0.08


def run_pv_bess(req) -> dict:
    """PV + BESS fizibilite analizini çalıştırır ve route ile birebir aynı
    yanıt sözlüğünü döndürür. `req` attribute-erişimli bir nesnedir."""
    pv_profile = simulate_pv_production(
        req.latitude, req.longitude,
        req.panel_kw, req.tilt, req.azimuth,
    )
    # Taban yük profili (paydaş tipine göre BDEW şekli). annual_consumption_kwh
    # EV HARİÇ taban tüketimdir; EV varsa akşam-yoğun profili ayrıca eklenir
    # (çift sayım yok, EV enerjisi kendi akşam şeklini alır).
    load_profile = generate_load_profile(req.stakeholder_type, req.annual_consumption_kwh)
    ev_annual_kwh = getattr(req, "ev_annual_kwh", None) or 0.0
    if ev_annual_kwh > 0:
        from app.simulation.loads.ev_load import ev_charging_profile
        load_profile = load_profile + ev_charging_profile(ev_annual_kwh)
    total_consumption_kwh = req.annual_consumption_kwh + ev_annual_kwh

    battery = BatteryModel(
        capacity_kwh=req.bess_kwh,
        chemistry=req.bess_chemistry,
    )
    bess_result = battery.dispatch_self_consumption(pv_profile, load_profile)

    # Tarife: kullanıcı değeri varsa EPDK varsayılanını ezer
    tariff = get_simple_tariff()
    buy = getattr(req, "electricity_buy_price_tl_per_kwh", None)
    sell = getattr(req, "electricity_sell_price_tl_per_kwh", None)
    if buy is not None:
        tariff['day_rate_tl_per_kwh'] = buy
        tariff['night_rate_tl_per_kwh'] = buy
    if sell is not None:
        tariff['export_rate_tl_per_kwh'] = sell

    # Mahsuplaşma netleme aralığı: mesken=aylık, ticarethane=saatlik (TR rejimi);
    # istek override edebilir (netting_interval)
    from app.simulation.loads.turkey_parameters import netting_interval_for
    netting_interval = (getattr(req, "netting_interval", None)
                        or netting_interval_for(req.stakeholder_type))
    cashflow = simulate_annual_cashflow(pv_profile, bess_result, load_profile, tariff,
                                        netting_interval=netting_interval)
    annual_savings = cashflow['annual_savings_tl']

    # Sistem maliyeti: önce kullanıcı değeri, yoksa birim CAPEX'ten hesapla
    system_cost_tl = getattr(req, "system_cost_tl", None)
    pv_capex = getattr(req, "pv_capex_per_kwp", None)
    bess_capex = getattr(req, "battery_capex_per_kwh", None)
    if system_cost_tl is None:
        pv_capex_eff = pv_capex if pv_capex is not None else DEFAULT_PV_CAPEX_PER_KWP
        bess_capex_eff = bess_capex if bess_capex is not None else DEFAULT_BESS_CAPEX_PER_KWH
        system_cost_tl = req.panel_kw * pv_capex_eff + req.bess_kwh * bess_capex_eff

    # 25 yıllık nakit akışı: yıl 0 = -yatırım, yıl 1..N = tarife artışlı tasarruf
    cash_flows = [-system_cost_tl] + [
        annual_savings * (1 + TARIFF_GROWTH_RATE) ** y for y in range(req.lifetime_years)
    ]

    npv = calculate_npv(cash_flows, req.discount_rate)
    irr = calculate_irr(cash_flows)
    payback = calculate_payback_period(cash_flows, req.discount_rate)
    lcoe = calculate_lcoe(
        cashflow['total_production_kwh'],
        system_cost_tl,
        req.lifetime_years,
        req.discount_rate,
    )

    return {
        "annual_savings_tl": annual_savings,
        "simple_payback_years": payback['simple'],
        "discounted_payback_years": payback['discounted'],
        "npv_tl": round(npv, 2),
        "irr_percent": round(irr * 100, 2) if not np.isnan(irr) else None,
        "lcoe_tl_per_kwh": round(lcoe, 4),
        "self_consumption_ratio": cashflow['self_consumption_ratio'],
        "annual_production_kwh": cashflow['total_production_kwh'],
        "total_grid_import_kwh": cashflow['total_grid_import_kwh'],
        "total_grid_export_kwh": cashflow['total_grid_export_kwh'],
        "system_cost_tl": system_cost_tl,
        "assumptions": {
            "tariff_growth_rate": TARIFF_GROWTH_RATE,
            "discount_rate": req.discount_rate,
            "lifetime_years": req.lifetime_years,
            "electricity_buy_price_tl_per_kwh": tariff['day_rate_tl_per_kwh'],
            "electricity_sell_price_tl_per_kwh": tariff['export_rate_tl_per_kwh'],
            "pv_capex_per_kwp": pv_capex if pv_capex is not None else DEFAULT_PV_CAPEX_PER_KWP,
            "battery_capex_per_kwh": bess_capex if bess_capex is not None else DEFAULT_BESS_CAPEX_PER_KWH,
            "annual_consumption_kwh": total_consumption_kwh,
            "ev_annual_kwh": ev_annual_kwh,
        },
        # A23: ışınım veri-kaynağı (metin alanları — provenance grafı sayısal olmayanı almaz)
        **irradiance_provenance(req.latitude, req.longitude),
    }
