import numpy as np
from scipy import optimize

from app.simulation.compat import july_2026_replay


def calculate_npv(cash_flows: list, discount_rate: float) -> float:
    """Calculates Net Present Value of a cash flow series."""
    npv = 0.0
    for t, cf in enumerate(cash_flows):
        npv += cf / (1 + discount_rate) ** t
    return npv


def calculate_irr(cash_flows: list) -> float:
    """Calculates Internal Rate of Return using Brent's method."""
    try:
        irr = optimize.brentq(
            lambda r: calculate_npv(cash_flows, r),
            -0.5, 10.0,
            maxiter=500
        )
        return irr
    except (ValueError, RuntimeError):
        return float('nan')


def calculate_payback_period(cash_flows: list, discount_rate: float = 0.0) -> dict:
    """
    Calculates simple and discounted payback period.
    cash_flows[0] is the initial investment (negative).
    Returns: {"simple": years, "discounted": years}
    """
    cumulative_simple = 0.0
    cumulative_discounted = 0.0
    simple_payback = None
    discounted_payback = None

    for t, cf in enumerate(cash_flows):
        cumulative_simple += cf
        cumulative_discounted += cf / (1 + discount_rate) ** t if discount_rate > 0 else cf
        if simple_payback is None and cumulative_simple >= 0:
            simple_payback = float(t)
        if discounted_payback is None and cumulative_discounted >= 0:
            discounted_payback = float(t)

    # None = nakit akışı ufku içinde geri ödemiyor (JSON-güvenli; inf serileştirilemez
    # ve gerçek tarifeyle [A0] düşük-tasarruf senaryolarında meşru olarak oluşur)
    return {
        "simple": simple_payback,
        "discounted": discounted_payback,
    }


def calculate_lcoe(
    annual_production_kwh: float,
    total_cost_tl: float,
    lifetime_years: int,
    discount_rate: float
) -> float:
    """Levelized Cost of Energy (TL/kWh)."""
    if annual_production_kwh <= 0:
        return float('inf')
    annuity_factor = sum(1 / (1 + discount_rate) ** t for t in range(1, lifetime_years + 1))
    lcoe = total_cost_tl / (annual_production_kwh * annuity_factor)
    return lcoe


def calculate_lcos(
    annual_cycles: float,
    total_cost_tl: float,
    lifetime_cycles: float,
    efficiency: float
) -> float:
    """Levelized Cost of Storage (TL/kWh-cycle)."""
    if lifetime_cycles <= 0 or efficiency <= 0:
        return float('inf')
    return total_cost_tl / (lifetime_cycles * efficiency)


# Netleme (mahsuplaşma) — periyot uzunlukları (8760 saatlik yıl; artık-yıl değil)
_DAYS_IN_MONTH = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


def _period_ids(n_hours: int, interval: str) -> np.ndarray:
    """Saat indekslerini netleme-periyoduna eşler (hourly/daily/monthly/annual)."""
    if interval == "hourly":
        return np.arange(n_hours)
    if interval == "daily":
        return np.arange(n_hours) // 24
    if interval == "annual":
        return np.zeros(n_hours, dtype=int)
    if interval == "monthly":
        ids = np.empty(n_hours, dtype=int)
        h = 0
        for m, d in enumerate(_DAYS_IN_MONTH):
            hrs = min(d * 24, n_hours - h)
            if hrs <= 0:
                break
            ids[h:h + hrs] = m
            h += hrs
        if h < n_hours:                      # 8760 dışı diziler: kalanı son aya
            ids[h:] = len(_DAYS_IN_MONTH) - 1
        return ids
    raise ValueError(f"bilinmeyen netting_interval: {interval!r}")


def apply_netting(grid_import_kwh: np.ndarray, grid_export_kwh: np.ndarray,
                  netting_interval: str) -> tuple:
    """Mahsuplaşma: netleme aralığı içinde import ve export'u KARŞILIKLI mahsup eder.

    Aylık netlemede öğle üretim-fazlası aynı ay içindeki akşam tüketimini PERAKENDE
    değerinde örter; yalnız periyot-net-fazlası ihraç edilir → PV lehine.
    Saatlik netlemede her saat ayrı → anlık fazla ihraç edilir (mahsup yok).

    Döner: (faturalanan_import_kwh, faturalanan_export_kwh). Saatlik-BESS sonrası
    bir periyotta hem import hem export olabilir (öğle export + akşam import);
    offset=min(import,export) mahsup edilen kısımdır.
    """
    imp = np.asarray(grid_import_kwh, dtype=float)
    exp = np.asarray(grid_export_kwh, dtype=float)
    ids = _period_ids(len(imp), netting_interval)
    billed_imp = 0.0
    billed_exp = 0.0
    for p in np.unique(ids):
        mask = ids == p
        pi = float(imp[mask].sum())
        pe = float(exp[mask].sum())
        offset = pi if pi < pe else pe       # min(import, export) → perakende mahsubu
        billed_imp += pi - offset
        billed_exp += pe - offset
    return billed_imp, billed_exp


def simulate_annual_cashflow(
    pv_profile_kwh: np.ndarray,
    bess_result: dict,
    load_profile_kwh: np.ndarray,
    tariff: dict,
    netting_interval: str = "hourly",
) -> dict:
    """
    Calculates annual financial return from PV+BESS system.

    tariff dict keys:
        day_rate_tl_per_kwh    - daytime electricity rate
        night_rate_tl_per_kwh  - nighttime rate (simplified: same as day for now)
        export_rate_tl_per_kwh - net metering export rate
        vat_rate               - e.g. 0.20 for %20

    netting_interval — mahsuplaşma aralığı ('hourly'|'daily'|'monthly'|'annual').
        Mesken TR rejiminde 'monthly' (aylık), ticarethane 'hourly' (saatlik);
        bkz. loads.turkey_parameters.netting_interval_for. Saatlik BESS dispatch
        sonrası grid_import/export bu aralıkta yeniden netlenir.
    """
    grid_import = np.asarray(bess_result['grid_import_kwh'], dtype=float)
    grid_export = np.asarray(bess_result['grid_export_kwh'], dtype=float)

    rate = tariff.get('day_rate_tl_per_kwh', 5.0)
    export_rate = tariff.get('export_rate_tl_per_kwh', rate)
    vat = tariff.get('vat_rate', 0.20)
    # A27: KDV-dahil fiyata ('vat_included', ör. get_simple_tariff) KDV yeniden eklenmez;
    # Temmuz-replay eski çift-KDV davranışını korur (app.simulation.compat)
    vat_mult = 1.0 if (tariff.get('vat_included') and not july_2026_replay()) else (1 + vat)

    # Mahsuplaşma: netleme aralığında import/export karşılıklı mahsup edilir
    billed_import_kwh, billed_export_kwh = apply_netting(
        grid_import, grid_export, netting_interval)
    netting_offset_kwh = float(grid_import.sum()) - billed_import_kwh  # perakende-mahsup

    # Cost without solar (pay full load from grid)
    cost_without_solar_tl = load_profile_kwh.sum() * rate * vat_mult

    # Cost with solar + BESS (faturalanan — netleme sonrası)
    import_cost_tl = billed_import_kwh * rate * vat_mult
    export_revenue_tl = billed_export_kwh * export_rate

    annual_savings_tl = cost_without_solar_tl - import_cost_tl + export_revenue_tl

    total_production_kwh = pv_profile_kwh.sum()
    self_consumption_ratio = bess_result.get('self_consumption_ratio', 0.0)

    return {
        "annual_savings_tl": round(annual_savings_tl, 2),
        "cost_without_solar_tl": round(cost_without_solar_tl, 2),
        "import_cost_tl": round(import_cost_tl, 2),
        "export_revenue_tl": round(export_revenue_tl, 2),
        "total_production_kwh": round(total_production_kwh, 2),
        "total_grid_import_kwh": round(float(grid_import.sum()), 2),
        "total_grid_export_kwh": round(float(grid_export.sum()), 2),
        "self_consumption_ratio": round(self_consumption_ratio, 4),
        "netting_interval": netting_interval,
        "billed_import_kwh": round(billed_import_kwh, 2),
        "billed_export_kwh": round(billed_export_kwh, 2),
        "netting_offset_kwh": round(netting_offset_kwh, 2),
    }
