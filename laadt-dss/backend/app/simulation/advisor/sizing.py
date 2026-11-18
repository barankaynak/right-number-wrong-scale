"""
LAaDT-DSS — Heuristic PV + BESS Sizing Advisor
===============================================
Pure heuristic functions (no network / DB I/O) that convert non-expert
inputs (roof area, monthly bill, consumption) into a recommended solar
(GES/PV) + battery (BESS) system specification.

All Turkish electricity tariff constants are intentionally imported from
the single authoritative source (turkey_2026.py) so that forward
(bill calculation) and reverse (bill inversion) logic can never diverge.
"""

import math
from typing import Optional

from app.simulation.economic.tariffs.turkey_2026 import (
    RESIDENTIAL_TIERS,
    VAT_RATE,
    FLAT_RATE_TL_PER_KWH,
    calculate_tiered_bill,
)

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

PANEL_AREA_M2: float = 2.0           # footprint of one 400 W panel (m²)
PANEL_KW: float = 0.40               # rated power per panel (kWp)
USABLE_ROOF_FACTOR: float = 0.70     # fraction of gross roof area that is usable
SPECIFIC_YIELD_KWH_PER_KWP: float = 1400.0  # conservative Turkey annual yield

KWH_PER_KWP_MIN: float = 1.0        # lower bound of battery-to-PV ratio
KWH_PER_KWP_MAX: float = 2.5        # upper bound of battery-to-PV ratio
BESS_MODULE_KWH: float = 4.8        # granularity for rounding battery capacity

# Fraction of daily load that occurs in the evening (after sunset) —
# determines the autonomy target for battery sizing.
EVENING_LOAD_FRACTION: dict[str, float] = {
    "residential": 0.35,
    "commercial":  0.15,
    "municipal":   0.55,
    "utility":     0.20,
}


# ---------------------------------------------------------------------------
# 1. Roof area → installed PV capacity
# ---------------------------------------------------------------------------

def roof_area_to_kwp(roof_area_m2: float) -> dict:
    """Convert gross roof area to installable PV capacity.

    usable_area = roof_area_m2 * USABLE_ROOF_FACTOR
    panel_count = floor(usable_area / PANEL_AREA_M2)
    kwp         = panel_count * PANEL_KW

    Parameters
    ----------
    roof_area_m2 : float
        Total (gross) roof area available for panels, in m².

    Returns
    -------
    dict
        {'panel_count': int, 'kwp': float, 'usable_area_m2': float}
    """
    if roof_area_m2 < 0:
        raise ValueError(f"roof_area_m2 must be non-negative, got {roof_area_m2}")

    usable_area_m2 = roof_area_m2 * USABLE_ROOF_FACTOR
    panel_count = int(math.floor(usable_area_m2 / PANEL_AREA_M2))
    kwp = panel_count * PANEL_KW

    return {
        "panel_count": panel_count,
        "kwp": kwp,
        "usable_area_m2": usable_area_m2,
    }


# ---------------------------------------------------------------------------
# 2. Monthly bill → monthly consumption (inverse of calculate_tiered_bill)
# ---------------------------------------------------------------------------

def invert_tiered_bill(monthly_bill_tl: float) -> float:
    """Reverse of calculate_tiered_bill for RESIDENTIAL tiers.

    Algorithm
    ---------
    1. Strip VAT:  pre_vat_bill = monthly_bill_tl / (1 + VAT_RATE)
    2. Walk RESIDENTIAL_TIERS in order.  For each tier, compute the
       maximum cost that tier can contribute (tier_size * rate).
       • If the remaining bill exceeds that maximum, the consumer used
         the full tier: consume tier_size kWh, subtract the tier cost.
       • Otherwise, the remaining bill falls inside this tier:
         add remaining_bill / rate kWh and stop.
    3. The unbounded top tier (limit_kwh = inf) has no tier_size cap;
       consumption there = remaining_bill / rate.

    Must satisfy:
        invert_tiered_bill(calculate_tiered_bill(x)) ≈ x   for x ≥ 0

    Parameters
    ----------
    monthly_bill_tl : float
        Gross monthly bill in TL (VAT included).

    Returns
    -------
    float
        Estimated monthly electricity consumption in kWh.
    """
    if monthly_bill_tl < 0:
        raise ValueError(f"monthly_bill_tl must be non-negative, got {monthly_bill_tl}")

    pre_vat_bill = monthly_bill_tl / (1.0 + VAT_RATE)
    remaining_bill = pre_vat_bill
    total_kwh = 0.0
    prev_limit = 0.0

    for tier in RESIDENTIAL_TIERS:
        limit = tier["limit_kwh"]
        rate = tier["rate_tl_per_kwh"]

        if math.isinf(limit):
            # Unbounded top tier — all remaining bill goes here
            total_kwh += remaining_bill / rate
            remaining_bill = 0.0
            break

        tier_size = limit - prev_limit          # kWh capacity of this tier
        tier_cost = tier_size * rate            # maximum cost this tier can contribute

        if remaining_bill <= tier_cost:
            # Consumption falls within this tier
            total_kwh += remaining_bill / rate
            remaining_bill = 0.0
            break
        else:
            # Consumer filled this entire tier
            total_kwh += tier_size
            remaining_bill -= tier_cost

        prev_limit = limit

    # remaining_bill > 0 here would mean bill exceeded all tiers — shouldn't
    # happen with a well-formed RESIDENTIAL_TIERS that has an inf-limit top tier.
    if remaining_bill > 1e-6:
        # Fallback: add whatever is left using the last rate
        last_rate = RESIDENTIAL_TIERS[-1]["rate_tl_per_kwh"]
        total_kwh += remaining_bill / last_rate

    return total_kwh


# ---------------------------------------------------------------------------
# 3. Bill / consumption inputs → annual consumption
# ---------------------------------------------------------------------------

def bill_to_annual_consumption(
    monthly_bill_tl: Optional[float] = None,
    monthly_consumption_kwh: Optional[float] = None,
    annual_consumption_kwh: Optional[float] = None,
    stakeholder_type: str = "residential",
) -> float:
    """Resolve one of several user inputs to annual electricity consumption.

    Priority (highest first):
        1. annual_consumption_kwh — used directly if provided.
        2. monthly_consumption_kwh — multiplied by 12.
        3. monthly_bill_tl:
           • residential  → invert_tiered_bill(monthly_bill_tl) * 12
           • others       → (monthly_bill_tl / (FLAT_RATE_TL_PER_KWH * (1 + VAT_RATE))) * 12

    Raises
    ------
    ValueError
        If none of the three inputs is provided.
    """
    if annual_consumption_kwh is not None:
        return float(annual_consumption_kwh)

    if monthly_consumption_kwh is not None:
        return float(monthly_consumption_kwh) * 12.0

    if monthly_bill_tl is not None:
        if stakeholder_type == "residential":
            monthly_kwh = invert_tiered_bill(monthly_bill_tl)
        else:
            # Flat-rate inversion for commercial / municipal / utility
            effective_rate = FLAT_RATE_TL_PER_KWH * (1.0 + VAT_RATE)
            monthly_kwh = monthly_bill_tl / effective_rate
        return monthly_kwh * 12.0

    raise ValueError(
        "At least one of annual_consumption_kwh, monthly_consumption_kwh, "
        "or monthly_bill_tl must be provided."
    )


# ---------------------------------------------------------------------------
# 4. Demand-based PV sizing
# ---------------------------------------------------------------------------

def demand_to_kwp(annual_consumption_kwh: float) -> float:
    """Size PV system to offset ~100 % of annual consumption.

    recommended_kwp = annual_consumption_kwh / SPECIFIC_YIELD_KWH_PER_KWP

    Parameters
    ----------
    annual_consumption_kwh : float
        Annual electricity consumption in kWh.

    Returns
    -------
    float
        Required PV capacity in kWp.
    """
    if annual_consumption_kwh < 0:
        raise ValueError(f"annual_consumption_kwh must be non-negative, got {annual_consumption_kwh}")
    return annual_consumption_kwh / SPECIFIC_YIELD_KWH_PER_KWP


# ---------------------------------------------------------------------------
# 5. Battery sizing
# ---------------------------------------------------------------------------

def size_battery(
    annual_consumption_kwh: float,
    recommended_kwp: float,
    want_battery: bool,
    stakeholder_type: str = "residential",
) -> float:
    """Heuristic battery capacity recommendation.

    If want_battery is False, returns 0.0.

    Algorithm
    ---------
    daily_consumption = annual_consumption_kwh / 365
    evening_share     = EVENING_LOAD_FRACTION[stakeholder_type]
    autonomy_kwh      = daily_consumption * evening_share * 1.0  (1 day autonomy)

    Clamp:
        autonomy_kwh = max(recommended_kwp * KWH_PER_KWP_MIN,
                          min(autonomy_kwh, recommended_kwp * KWH_PER_KWP_MAX))

    Round up to nearest BESS_MODULE_KWH; ensure at least one module.

    Parameters
    ----------
    annual_consumption_kwh : float
    recommended_kwp : float
    want_battery : bool
    stakeholder_type : str

    Returns
    -------
    float
        Recommended BESS capacity in kWh (0.0 if no battery wanted).
    """
    if not want_battery:
        return 0.0

    evening_share = EVENING_LOAD_FRACTION.get(stakeholder_type, EVENING_LOAD_FRACTION["residential"])
    daily_consumption = annual_consumption_kwh / 365.0
    autonomy_kwh = daily_consumption * evening_share  # 1.0 × factor

    # Clamp to PV-proportional band
    lower = recommended_kwp * KWH_PER_KWP_MIN
    upper = recommended_kwp * KWH_PER_KWP_MAX
    autonomy_kwh = max(lower, min(autonomy_kwh, upper))

    # Round up to nearest BESS_MODULE_KWH, minimum one module
    modules = math.ceil(autonomy_kwh / BESS_MODULE_KWH)
    if modules < 1:
        modules = 1

    return modules * BESS_MODULE_KWH


# ---------------------------------------------------------------------------
# 6. Tilt recommendation
# ---------------------------------------------------------------------------

def recommend_default_tilt(latitude: float) -> float:
    """Return recommended panel tilt angle (degrees) for a given latitude.

    tilt = round(latitude), clamped to [10°, 35°].

    Parameters
    ----------
    latitude : float
        Site latitude in decimal degrees.

    Returns
    -------
    float
        Recommended tilt in degrees.
    """
    tilt = round(latitude)
    return float(max(10, min(tilt, 35)))


# ---------------------------------------------------------------------------
# 7. Top-level orchestrator
# ---------------------------------------------------------------------------

def recommend_system(
    latitude: float,
    longitude: float,
    stakeholder_type: str = "residential",
    roof_area_m2: Optional[float] = None,
    monthly_bill_tl: Optional[float] = None,
    monthly_consumption_kwh: Optional[float] = None,
    annual_consumption_kwh: Optional[float] = None,
    want_battery: bool = True,
    ev_annual_kwh: float = 0.0,
    override_kwp: Optional[float] = None,
    override_bess_kwh: Optional[float] = None,
    override_tilt: Optional[float] = None,
    override_azimuth: Optional[float] = None,
    override_chemistry: Optional[str] = None,
) -> dict:
    """Orchestrate heuristic PV + BESS sizing from non-expert inputs.

    Parameters
    ----------
    latitude, longitude : float
        Site coordinates (decimal degrees).
    stakeholder_type : str
        One of 'residential', 'commercial', 'municipal', 'utility'.
    roof_area_m2 : float, optional
        Gross roof area (m²). Used to cap PV capacity.
    monthly_bill_tl : float, optional
        Gross monthly electricity bill (TL, VAT included).
    monthly_consumption_kwh : float, optional
        Average monthly electricity consumption (kWh).
    annual_consumption_kwh : float, optional
        Annual electricity consumption (kWh).
    want_battery : bool
        Whether a battery system should be included.
    override_kwp : float, optional
        Force a specific PV capacity (kWp), bypassing heuristic sizing.
    override_bess_kwh : float, optional
        Force a specific battery capacity (kWh).
    override_tilt : float, optional
        Force a specific tilt angle (degrees).
    override_azimuth : float, optional
        Force a specific azimuth angle (degrees, 180 = south).
    override_chemistry : str, optional
        Force a specific battery chemistry (e.g. 'LFP', 'NMC', 'LTO').

    Returns
    -------
    dict with keys:
        kwp                  : float  — recommended PV capacity
        panel_count          : int    — number of 400 W panels
        bess_kwh             : float  — recommended battery capacity
        chemistry            : str    — battery chemistry
        tilt                 : float  — panel tilt (°)
        azimuth              : float  — panel azimuth (°, 180 = south)
        annual_consumption_kwh: float
        roof_capped          : bool   — True when roof area limits PV below demand
        demand_capped        : bool   — True when demand limits PV below roof capacity
        sizing_explained     : list[str] — short Turkish decision-rationale strings
    """
    explained: list[str] = []
    roof_capped = False
    demand_capped = False

    # --- Step 1: Resolve annual consumption (taban) ---
    base_kwh = bill_to_annual_consumption(
        monthly_bill_tl=monthly_bill_tl,
        monthly_consumption_kwh=monthly_consumption_kwh,
        annual_consumption_kwh=annual_consumption_kwh,
        stakeholder_type=stakeholder_type,
    )
    explained.append(f"Yıllık tüketim tahmini: {base_kwh:.0f} kWh")

    # --- Step 1b: EV ev-şarj yükü (varsa toplama eklenir) ---
    ev_kwh = max(0.0, float(ev_annual_kwh))
    ann_kwh = base_kwh + ev_kwh   # boyutlandırma (GES + batarya) toplam tüketime göre
    if ev_kwh > 0:
        explained.append(
            f"Elektrikli araç ev-şarjı: +{ev_kwh:.0f} kWh/yıl → toplam {ann_kwh:.0f} kWh "
            f"(akşam-yoğun şarj, boyutlandırma buna göre yapılır)."
        )

    # --- Step 2: Demand-based PV sizing ---
    demand_kwp = demand_to_kwp(ann_kwh)
    explained.append(
        f"Talep bazlı GES boyutu: {demand_kwp:.2f} kWp "
        f"({SPECIFIC_YIELD_KWH_PER_KWP:.0f} kWh/kWp özgül verim varsayımı)"
    )

    # --- Step 3: Roof-constrained PV sizing ---
    roof_kwp: Optional[float] = None
    roof_panel_count: Optional[int] = None
    if roof_area_m2 is not None:
        roof_info = roof_area_to_kwp(roof_area_m2)
        roof_kwp = roof_info["kwp"]
        roof_panel_count = roof_info["panel_count"]
        explained.append(
            f"Çatı alanı ({roof_area_m2:.0f} m²) → "
            f"kullanılabilir {roof_info['usable_area_m2']:.1f} m² → "
            f"{roof_panel_count} panel → {roof_kwp:.2f} kWp"
        )

    # --- Step 4: Choose recommended_kwp (min of demand and roof) ---
    if override_kwp is not None:
        recommended_kwp = float(override_kwp)
        panel_count = round(recommended_kwp / PANEL_KW)
        explained.append(f"GES kapasitesi kullanıcı tarafından {recommended_kwp:.2f} kWp olarak belirlendi.")
    elif roof_kwp is not None:
        if roof_kwp < demand_kwp:
            recommended_kwp = roof_kwp
            panel_count = roof_panel_count  # type: ignore[assignment]
            roof_capped = True
            explained.append(
                f"Çatı alanı kısıtı aktif: {roof_kwp:.2f} kWp < "
                f"talep bazlı {demand_kwp:.2f} kWp → {roof_kwp:.2f} kWp seçildi."
            )
        else:
            recommended_kwp = demand_kwp
            panel_count = round(demand_kwp / PANEL_KW)
            demand_capped = True
            explained.append(
                f"Talep kısıtı aktif: {demand_kwp:.2f} kWp < "
                f"çatı kapasitesi {roof_kwp:.2f} kWp → {demand_kwp:.2f} kWp seçildi."
            )
    else:
        recommended_kwp = demand_kwp
        panel_count = round(demand_kwp / PANEL_KW)
        explained.append(f"Çatı alanı verilmedi; talep bazlı {recommended_kwp:.2f} kWp kullanıldı.")

    # --- Step 5: Battery sizing ---
    if override_bess_kwh is not None:
        bess_kwh = float(override_bess_kwh)
        explained.append(f"Batarya kapasitesi kullanıcı tarafından {bess_kwh:.1f} kWh olarak belirlendi.")
    else:
        bess_kwh = size_battery(ann_kwh, recommended_kwp, want_battery, stakeholder_type)
        if want_battery:
            explained.append(
                f"Batarya boyutu: {bess_kwh:.1f} kWh "
                f"(akşam yük payı {EVENING_LOAD_FRACTION.get(stakeholder_type, 0.35):.0%}, "
                f"BESS modül={BESS_MODULE_KWH} kWh)"
            )
        else:
            explained.append("Batarya sistemi istenmedi; BESS = 0 kWh.")

    # --- Step 6: Tilt ---
    if override_tilt is not None:
        tilt = float(override_tilt)
        explained.append(f"Panel eğimi kullanıcı tarafından {tilt:.1f}° olarak belirlendi.")
    else:
        tilt = recommend_default_tilt(latitude)
        explained.append(f"Önerilen panel eğimi: {tilt:.1f}° (enlem {latitude:.1f}° bazında).")

    # --- Step 7: Azimuth ---
    if override_azimuth is not None:
        azimuth = float(override_azimuth)
        explained.append(f"Panel azimut açısı kullanıcı tarafından {azimuth:.1f}° olarak belirlendi.")
    else:
        azimuth = 180.0  # true south — optimal for Turkey
        explained.append("Azimut: 180° (güney yönü, Türkiye için optimum).")

    # --- Step 8: Battery chemistry ---
    if override_chemistry is not None:
        chemistry = str(override_chemistry)
        explained.append(f"Batarya kimyası kullanıcı tarafından '{chemistry}' olarak belirlendi.")
    else:
        chemistry = "LFP"
        explained.append("Batarya kimyası: LFP (uzun ömür, güvenli, konut/ticari uygulamalar için önerilen).")

    return {
        "kwp": recommended_kwp,
        "panel_count": panel_count,
        "bess_kwh": bess_kwh,
        "chemistry": chemistry,
        "tilt": tilt,
        "azimuth": azimuth,
        "annual_consumption_kwh": ann_kwh,        # toplam (taban + EV) — gösterim & boyutlandırma
        "base_consumption_kwh": base_kwh,          # EV hariç taban — yük profili şekli için
        "ev_annual_kwh": ev_kwh,                   # EV ev-şarjı (0 ise yok)
        "roof_capped": roof_capped,
        "demand_capped": demand_capped,
        "sizing_explained": explained,
    }


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import pprint

    # Round-trip test: invert_tiered_bill must be the exact inverse of
    # calculate_tiered_bill to within 1 kWh.
    test_kwh = 250.0
    bill = calculate_tiered_bill(test_kwh)
    recovered = invert_tiered_bill(bill)
    assert abs(recovered - test_kwh) < 1.0, (
        f"Round-trip FAILED: calculate_tiered_bill({test_kwh}) = {bill:.4f} TL, "
        f"invert_tiered_bill({bill:.4f}) = {recovered:.4f} kWh "
        f"(error = {abs(recovered - test_kwh):.4f} kWh)"
    )
    print(f"[OK] Round-trip test passed: 250 kWh → {bill:.2f} TL → {recovered:.2f} kWh")

    # Additional boundary checks
    for kwh in [0.0, 75.0, 150.0, 151.0, 300.0, 400.0, 401.0, 800.0]:
        b = calculate_tiered_bill(kwh)
        r = invert_tiered_bill(b)
        assert abs(r - kwh) < 1.0, f"Round-trip FAILED at {kwh} kWh: got {r:.4f}"
    print("[OK] Boundary round-trip tests passed (0, 75, 150, 151, 300, 400, 401, 800 kWh).")

    # Full system recommendation demo
    print("\n--- recommend_system demo (Antalya, 60 m² çatı, 1500 TL/ay fatura) ---")
    result = recommend_system(
        latitude=36.9,
        longitude=30.7,
        roof_area_m2=60,
        monthly_bill_tl=1500,
    )
    pprint.pprint(result)
