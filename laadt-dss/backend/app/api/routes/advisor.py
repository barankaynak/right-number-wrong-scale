"""
Advisor (rehberli karar destek) route'ları.

Uzman olmayan kullanıcı için otomatik boyutlandırma + fizibilite:
- POST /api/v1/advisor/panel-layout  → çatı poligonundan düzenlenebilir panel dizilimi
- POST /api/v1/advisor/recommend     → konum + (çatı | fatura | kWh) → sistem önerisi + fizibilite + sade dil

Tüm sayısal sonuçlar mevcut fizik motorlarından gelir (LLM değil).
"""

from types import SimpleNamespace
from typing import Optional, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.simulation.advisor import sizing, panel_layout
from app.simulation.advisor.feasibility_service import run_pv_bess
from app.simulation.advisor.region_network import simulate_region
from app.simulation.policy.policy_engine import compare_policies
from app.simulation.loads.turkey_parameters import EV_ANNUAL_KWH_HOME
from app.core.cache import get_cached, set_cached

router = APIRouter(prefix="/api/v1/advisor", tags=["advisor"])


# ─── Panel Layout ────────────────────────────────────────────────────────────────

class PanelLayoutRequest(BaseModel):
    roof_polygon_lonlat: List[List[float]] = Field(..., description="[[lon,lat], ...] çatı poligonu")
    azimuth_deg: float = Field(180.0, ge=0, le=360)
    tilt_deg: float = Field(30.0, ge=0, le=60)
    optimum: bool = Field(True, description="True ise en iyi yönelim otomatik seçilir")
    max_panels: Optional[int] = Field(None, ge=1)


@router.post("/panel-layout", summary="Çatıya düzenlenebilir panel dizilimi")
def panel_layout_endpoint(req: PanelLayoutRequest):
    try:
        if len(req.roof_polygon_lonlat) < 3:
            raise ValueError("Çatı poligonu en az 3 nokta içermeli")
        if req.optimum:
            result = panel_layout.optimum_layout(
                req.roof_polygon_lonlat, tilt_deg=req.tilt_deg, max_panels=req.max_panels,
            )
        else:
            result = panel_layout.generate_layout(
                req.roof_polygon_lonlat, azimuth_deg=req.azimuth_deg,
                tilt_deg=req.tilt_deg, max_panels=req.max_panels,
            )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Recommend (boyutlandır + simüle et) ──────────────────────────────────────────

class AdvisorRequest(BaseModel):
    latitude: float
    longitude: float
    stakeholder_type: str = Field("residential", description="residential|commercial|municipal|utility")
    # Tüketim girdisi (en az biri)
    roof_area_m2: Optional[float] = Field(None, ge=1)
    monthly_bill_tl: Optional[float] = Field(None, ge=1)
    monthly_consumption_kwh: Optional[float] = Field(None, ge=1)
    annual_consumption_kwh: Optional[float] = Field(None, ge=1)
    want_battery: bool = True
    compare_storage: bool = Field(False, description="True ise bataryalı + bataryasız iki sonuç döner")
    # Elektrikli araç ev-şarjı (akşam-yoğun ek yük)
    has_ev: bool = Field(False, description="True ise haneye EV ev-şarj yükü eklenir")
    ev_annual_kwh: Optional[float] = Field(None, ge=0, le=50000, description="EV yıllık ev-şarj enerjisi (boşsa varsayılan ~3000 kWh)")
    # Kullanıcı kararları (override → otomatik öneriyi ezer)
    override_kwp: Optional[float] = Field(None, gt=0)
    override_bess_kwh: Optional[float] = Field(None, ge=0)
    override_tilt: Optional[float] = Field(None, ge=0, le=60)
    override_azimuth: Optional[float] = Field(None, ge=0, le=360)
    override_chemistry: Optional[str] = Field(None, description="LFP|NMC|LTO")
    # Ekonomik override'lar
    discount_rate: float = Field(0.10, ge=0, le=1)
    lifetime_years: int = Field(25, ge=1, le=40)
    electricity_buy_price_tl_per_kwh: Optional[float] = Field(None, ge=0.1, le=100)
    electricity_sell_price_tl_per_kwh: Optional[float] = Field(None, ge=0.0, le=100)
    pv_capex_per_kwp: Optional[float] = Field(None, ge=1000, le=500000)
    battery_capex_per_kwh: Optional[float] = Field(None, ge=1000, le=500000)


def _build_feasibility_req(rec: dict, req: AdvisorRequest, bess_kwh: float) -> SimpleNamespace:
    return SimpleNamespace(
        latitude=req.latitude, longitude=req.longitude,
        panel_kw=rec['kwp'], tilt=rec['tilt'], azimuth=rec['azimuth'],
        bess_kwh=bess_kwh, bess_chemistry=rec['chemistry'],
        # Taban tüketim (EV hariç) + ayrı EV enerjisi → run_pv_bess EV'yi akşam
        # profiliyle ekler (çift sayım yok, toplam assumptions'ta raporlanır).
        annual_consumption_kwh=rec.get('base_consumption_kwh', rec['annual_consumption_kwh']),
        ev_annual_kwh=rec.get('ev_annual_kwh', 0.0),
        stakeholder_type=req.stakeholder_type,
        discount_rate=req.discount_rate, lifetime_years=req.lifetime_years,
        system_cost_tl=None,
        electricity_buy_price_tl_per_kwh=req.electricity_buy_price_tl_per_kwh,
        electricity_sell_price_tl_per_kwh=req.electricity_sell_price_tl_per_kwh,
        pv_capex_per_kwp=req.pv_capex_per_kwp,
        battery_capex_per_kwh=req.battery_capex_per_kwh,
    )


def _plain_language(rec: dict, feas: dict) -> dict:
    payback = feas.get('simple_payback_years')
    npv = feas.get('npv_tl', 0)
    savings = feas.get('annual_savings_tl', 0)
    kwp = rec['kwp']
    bess = rec['bess_kwh']
    headline = f"{kwp:.1f} kWp güneş paneli" + (f" + {bess:.1f} kWh batarya" if bess > 0 else "")
    if payback is None or payback <= 0:
        payback_sentence = "Geri ödeme süresi hesaplanamadı."
    else:
        payback_sentence = f"Yatırımınız yaklaşık {payback:.1f} yılda kendini amorti eder."
    savings_sentence = f"İlk yıl tahmini tasarruf: {savings:,.0f} TL."
    if npv > 0 and payback and payback < 12:
        verdict = "Kârlı yatırım"
    elif npv > 0:
        verdict = "Makul yatırım"
    else:
        verdict = "Mevcut koşullarda zorlayıcı"
    return {
        "headline": headline,
        "payback_sentence": payback_sentence,
        "savings_sentence": savings_sentence,
        "verdict": verdict,
    }


@router.post("/recommend", summary="Otomatik sistem önerisi + fizibilite")
def recommend(req: AdvisorRequest):
    cache_key = req.model_dump()
    cache_key['latitude'] = round(req.latitude, 4)
    cache_key['longitude'] = round(req.longitude, 4)
    cached = get_cached(cache_key)
    if cached is not None:
        return cached

    try:
        # EV ev-şarjı: has_ev=True ise ev_annual_kwh (yoksa Türkiye varsayılanı ~3000 kWh)
        ev_kwh = (req.ev_annual_kwh if req.ev_annual_kwh is not None else EV_ANNUAL_KWH_HOME) if req.has_ev else 0.0
        rec = sizing.recommend_system(
            latitude=req.latitude, longitude=req.longitude,
            stakeholder_type=req.stakeholder_type,
            roof_area_m2=req.roof_area_m2,
            monthly_bill_tl=req.monthly_bill_tl,
            monthly_consumption_kwh=req.monthly_consumption_kwh,
            annual_consumption_kwh=req.annual_consumption_kwh,
            want_battery=req.want_battery,
            ev_annual_kwh=ev_kwh,
            override_kwp=req.override_kwp, override_bess_kwh=req.override_bess_kwh,
            override_tilt=req.override_tilt, override_azimuth=req.override_azimuth,
            override_chemistry=req.override_chemistry,
        )

        feas = run_pv_bess(_build_feasibility_req(rec, req, rec['bess_kwh']))
        response = {
            "recommendation": rec,
            "feasibility": feas,
            "plain_language": _plain_language(rec, feas),
        }

        if req.compare_storage:
            feas_no_batt = run_pv_bess(_build_feasibility_req(rec, req, 0.0))
            response["comparison"] = {
                "with_battery": {
                    "bess_kwh": rec['bess_kwh'],
                    "npv_tl": feas.get('npv_tl'),
                    "simple_payback_years": feas.get('simple_payback_years'),
                    "annual_savings_tl": feas.get('annual_savings_tl'),
                    "self_consumption_ratio": feas.get('self_consumption_ratio'),
                },
                "without_battery": {
                    "bess_kwh": 0.0,
                    "npv_tl": feas_no_batt.get('npv_tl'),
                    "simple_payback_years": feas_no_batt.get('simple_payback_years'),
                    "annual_savings_tl": feas_no_batt.get('annual_savings_tl'),
                    "self_consumption_ratio": feas_no_batt.get('self_consumption_ratio'),
                },
            }

        set_cached(cache_key, response)
        return response

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Region (dağıtım şirketi şebeke etkisi) ──────────────────────────────────────

class RegionBuilding(BaseModel):
    lon: float
    lat: float
    area_m2: float = Field(..., gt=0)


class TransformerIn(BaseModel):
    id: Optional[str] = None
    lon: float
    lat: float
    capacity_kva: Optional[float] = Field(None, gt=0, le=10000)


class RegionRequest(BaseModel):
    buildings: List[RegionBuilding] = Field(..., min_length=1, max_length=300)
    pv_adoption_pct: float = Field(40.0, ge=0, le=100)
    with_storage: bool = False
    stakeholder_type: str = Field("residential")
    run_hosting_capacity: bool = True
    # Uzman parametreleri
    load_growth_pct: float = Field(3.0, ge=0, le=20)
    deferral_years: int = Field(15, ge=1, le=40)
    # Düzenlenebilir trafolar (boşsa otomatik yerleştirilir)
    transformers: Optional[List[TransformerIn]] = None
    # Kablo güzergâh (uzunluk) override'ları: elle bükülen kablolar için
    edge_length_overrides: Optional[List[dict]] = None
    # EV yaygınlığı (%): hanelerin ne kadarında elektrikli araç ev şarjı var
    ev_penetration_pct: float = Field(0.0, ge=0, le=100)


@router.post("/region", summary="Bölge dağıtım şebekesi etki analizi (sentetik geo-şebeke)")
def region(req: RegionRequest):
    cache_params = req.model_dump()
    cached = get_cached(cache_params)
    if cached is not None:
        return cached
    try:
        result = simulate_region(
            buildings=[b.model_dump() for b in req.buildings],
            pv_adoption_pct=req.pv_adoption_pct,
            with_storage=req.with_storage,
            stakeholder_type=req.stakeholder_type,
            run_hosting_capacity=req.run_hosting_capacity,
            load_growth_pct=req.load_growth_pct,
            deferral_years=req.deferral_years,
            transformers=[t.model_dump() for t in req.transformers] if req.transformers else None,
            edge_length_overrides=req.edge_length_overrides,
            ev_penetration_pct=req.ev_penetration_pct,
        )
        set_cached(cache_params, result)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Policy (devlet / teşvik karşılaştırması) ────────────────────────────────────

# 9 teşvik mekanizması — Türkiye'ye uygun varsayılan parametrelerle (her biri tek mekanizma)
DEFAULT_POLICIES = [
    {"name": "Sermaye Sübvansiyonu (%30)", "incentives": [{"type": "capital_subsidy", "subsidy_pct": 30}]},
    {"name": "KDV İstisnası (%20)", "incentives": [{"type": "vat_exemption", "vat_rate": 0.20}]},
    {"name": "Net Mahsuplaşma (1:1)", "incentives": [{"type": "net_metering", "net_metering_ratio": 1.0}]},
    {"name": "Besleme Tarifesi (7 ₺/kWh)", "incentives": [{"type": "feed_in_tariff", "fit_rate_tl_per_kwh": 7.0}]},
    {"name": "Düşük Faizli Kredi", "incentives": [{"type": "low_interest_loan", "loan_pct": 80, "loan_rate_pct": 15, "loan_term_yr": 10, "market_rate_pct": 45}]},
    {"name": "Öz-tüketim Primi (0.5 ₺/kWh)", "incentives": [{"type": "self_consumption_premium", "premium_tl_per_kwh": 0.5}]},
    {"name": "Karbon Kredisi (500 ₺/ton)", "incentives": [{"type": "carbon_credit", "carbon_credit_tl_per_ton": 500}]},
    {"name": "Vergi İndirimi (%100)", "incentives": [{"type": "tax_deduction", "tax_deduction_pct": 100, "corporate_tax_rate": 0.25}]},
    {"name": "Kapasite Ödemesi (200 ₺/kW/yıl)", "incentives": [{"type": "capacity_payment", "capacity_payment_tl_per_kw_yr": 200}]},
]


def _policy_state_cost(incentives: list, ctx: dict, base_investment: float, lifetime: int) -> float:
    """Tek bir sistem için, teşvikin devlete ömür boyu maliyeti (TL).
    9 mekanizmanın hepsi için (engine yalnızca 3'ünü hesaplar)."""
    cost = 0.0
    for inc in incentives:
        t = inc.get("type", "")
        if t == "capital_subsidy":
            cost += base_investment * inc.get("subsidy_pct", 30) / 100.0
        elif t == "vat_exemption":
            cost += ctx["system_cost_pre_vat"] * inc.get("vat_rate", 0.20)
        elif t == "tax_deduction":
            cost += base_investment * inc.get("tax_deduction_pct", 100) / 100.0 * inc.get("corporate_tax_rate", 0.25)
        elif t == "net_metering":
            extra = max(0.0, inc.get("net_metering_ratio", 1.0) - 1.0)  # mevcut oran 1.0 varsayımı
            cost += ctx["annual_export_kwh"] * ctx["base_rate_tl_per_kwh"] * extra * lifetime
        elif t == "feed_in_tariff":
            fit = inc.get("fit_rate_tl_per_kwh", 3.0)
            cost += ctx["annual_export_kwh"] * max(0.0, fit - ctx["current_export_rate"]) * lifetime
        elif t == "capacity_payment":
            cost += ctx["system_kw"] * inc.get("capacity_payment_tl_per_kw_yr", 0) * lifetime
        elif t == "low_interest_loan":
            loan_amount = base_investment * inc.get("loan_pct", 80) / 100.0
            spread = max(0.0, inc.get("market_rate_pct", 45) - inc.get("loan_rate_pct", 15)) / 100.0
            cost += loan_amount * spread * inc.get("loan_term_yr", 10)
        elif t == "self_consumption_premium":
            cost += ctx["annual_self_consumed_kwh"] * inc.get("premium_tl_per_kwh", 0.5) * lifetime
        elif t == "carbon_credit":
            co2_tons = ctx["annual_production_kwh"] * 0.45 / 1000.0
            cost += co2_tons * inc.get("carbon_credit_tl_per_ton", 500) * lifetime
    return cost


class PolicyRequest(BaseModel):
    latitude: float
    longitude: float
    representative_kwp: float = Field(10.0, gt=0, le=1000)
    representative_bess_kwh: float = Field(13.0, ge=0, le=2000)
    bess_chemistry: str = "LFP"
    stakeholder_type: str = Field("residential")
    annual_consumption_kwh: float = Field(4000.0, gt=0)
    n_systems: int = Field(100, ge=1, le=1_000_000, description="Bölge/ulusal ölçek — devlet maliyeti bu kadar sistemle çarpılır")
    discount_rate: float = Field(0.10, ge=0, le=1)
    lifetime_years: int = Field(25, ge=1, le=40)


@router.post("/policy", summary="Teşvik mekanizması karşılaştırması (devlet perspektifi)")
def policy(req: PolicyRequest):
    cache_params = req.model_dump()
    cached = get_cached(cache_params)
    if cached is not None:
        return cached
    try:
        # 1) Temsili sistem fizibilitesi — sayılar fizik motorundan gelir
        feas_req = SimpleNamespace(
            latitude=req.latitude, longitude=req.longitude,
            panel_kw=req.representative_kwp, tilt=30.0, azimuth=180.0,
            bess_kwh=req.representative_bess_kwh, bess_chemistry=req.bess_chemistry,
            annual_consumption_kwh=req.annual_consumption_kwh,
            stakeholder_type=req.stakeholder_type,
            discount_rate=req.discount_rate, lifetime_years=req.lifetime_years,
            system_cost_tl=None,
            electricity_buy_price_tl_per_kwh=None, electricity_sell_price_tl_per_kwh=None,
            pv_capex_per_kwp=None, battery_capex_per_kwh=None,
        )
        feas = run_pv_bess(feas_req)

        base_investment = feas["system_cost_tl"]
        annual_savings = feas["annual_savings_tl"]
        production = feas["annual_production_kwh"]
        export = feas["total_grid_export_kwh"]
        self_consumed = max(0.0, production - export)
        tariff_growth = 0.08

        base_cashflows = [-base_investment] + [
            annual_savings * (1 + tariff_growth) ** y for y in range(req.lifetime_years)
        ]
        context = {
            "system_kw": req.representative_kwp,
            "annual_export_kwh": export,
            "annual_production_kwh": production,
            "annual_self_consumed_kwh": self_consumed,
            "base_rate_tl_per_kwh": feas["assumptions"]["electricity_buy_price_tl_per_kwh"],
            "current_export_rate": feas["assumptions"]["electricity_sell_price_tl_per_kwh"],
            "system_cost_pre_vat": base_investment / 1.20,
        }

        comp = compare_policies(base_cashflows, DEFAULT_POLICIES, context, req.discount_rate)

        # 2) Devlet maliyetini 9 mekanizmanın TÜMÜ için yeniden hesapla (engine yalnızca 3'ünü yapar),
        #    etkinlik/kaldıraç skorlarını güncelle, bölge ölçeğine çarp
        n = req.n_systems
        policy_by_name = {p["name"]: p["incentives"] for p in DEFAULT_POLICIES}
        for pr in comp["policy_results"]:
            incentives = policy_by_name.get(pr["policy_name"], [])
            state_cost = _policy_state_cost(incentives, context, base_investment, req.lifetime_years)
            pr["state_cost_tl"] = round(state_cost, 2)
            pr["state_cost_per_kw_tl"] = round(state_cost / context["system_kw"], 2) if context["system_kw"] > 0 else None
            pr["incentive_effectiveness_score"] = round(pr["npv_tl"] / state_cost, 4) if state_cost > 0 else None
            pr["leverage"] = round(pr["triggered_investment_tl"] / state_cost, 2) if state_cost > 0 else None
            pr["state_cost_total_tl"] = round(state_cost * n, 2)
            pr["triggered_investment_total_tl"] = round(pr["triggered_investment_tl"] * n, 2)
            pr["annual_co2_total_tons"] = round(pr["annual_co2_reduction_tons"] * n, 2)

        # En verimli (TL başına en yüksek NPV) — güncel state cost'a göre
        scored = [p for p in comp["policy_results"] if p["incentive_effectiveness_score"] is not None]
        comp["best_policy_by_effectiveness"] = (
            max(scored, key=lambda x: x["incentive_effectiveness_score"])["policy_name"] if scored else None
        )

        # 3) Sade dil
        by_npv = comp.get("best_policy_by_npv")
        by_eff = comp.get("best_policy_by_effectiveness")
        comp["scale"] = {"n_systems": n, "representative_kwp": req.representative_kwp,
                         "base_investment_tl": base_investment, "annual_savings_tl": annual_savings}
        comp["plain_language"] = {
            "best_for_investor": f"Yatırımcı için en kârlı teşvik: {by_npv}.",
            "best_for_state": f"Devlet bütçesi açısından en verimli (TL başına en çok fayda): {by_eff}.",
            "headline": f"{n:,} sistem için {len(DEFAULT_POLICIES)} teşvik mekanizması karşılaştırıldı.".replace(",", "."),
        }

        set_cached(cache_params, comp)
        return comp
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
