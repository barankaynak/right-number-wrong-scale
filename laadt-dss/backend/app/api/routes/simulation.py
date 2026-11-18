import hashlib
import json
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, List
import numpy as np

from app.simulation.pv.solar_model import simulate_pv_production
from app.simulation.pv.load_profile import generate_load_profile
from app.simulation.bess.battery_model import BatteryModel
from app.simulation.economic.economic_engine import (
    calculate_npv, calculate_irr, calculate_payback_period,
    calculate_lcoe, simulate_annual_cashflow
)
from app.simulation.economic.tariffs.turkey_2026 import get_simple_tariff
from app.simulation.grid.grid_model import simulate_grid_impact, run_penetration_analysis, simulate_transformer_deferral
from app.simulation.policy.policy_engine import compare_policies, apply_incentive
from app.simulation.economic.monte_carlo import run_monte_carlo
from app.simulation.advisor.feasibility_service import run_pv_bess
from app.core.cache import get_cached, set_cached

router = APIRouter(prefix="/api/v1/simulate", tags=["simulation"])


class PVRequest(BaseModel):
    latitude: float = Field(39.93, description="Enlem")
    longitude: float = Field(32.86, description="Boylam")
    panel_kw: float = Field(10.0, gt=0, description="Panel gücü (kW)")
    tilt: float = Field(30.0, ge=0, le=90)
    azimuth: float = Field(180.0, ge=0, le=360)
    panel_type: str = Field("monocrystalline", description="Panel tipi")


class PVBESSRequest(BaseModel):
    latitude: float = 39.93
    longitude: float = 32.86
    panel_kw: float = Field(10.0, gt=0)
    tilt: float = 30.0
    azimuth: float = 180.0
    bess_kwh: float = Field(14.4, ge=0)
    bess_chemistry: str = Field("LFP", description="LFP | NMC | LTO")
    annual_consumption_kwh: float = Field(5000.0, gt=0, description="Yıllık tüketim (kWh)")
    stakeholder_type: str = Field("residential")
    discount_rate: float = Field(0.12, ge=0, le=1)
    system_cost_tl: Optional[float] = Field(None, description="Toplam sistem maliyeti TL (verilmezse CAPEX'ten hesaplanır)")
    lifetime_years: int = Field(25, ge=1, le=40)
    # Kullanıcı tanımlı ekonomik parametreler (opsiyonel — verilmezse EPDK 2026 varsayılanları kullanılır)
    electricity_buy_price_tl_per_kwh: Optional[float] = Field(None, ge=0.1, le=100, description="Alım tarifesi TL/kWh")
    electricity_sell_price_tl_per_kwh: Optional[float] = Field(None, ge=0.0, le=100, description="İhracat tarifesi TL/kWh")
    pv_capex_per_kwp: Optional[float] = Field(None, ge=1000, le=500000, description="PV kurulum maliyeti TL/kWp")
    battery_capex_per_kwh: Optional[float] = Field(None, ge=1000, le=500000, description="Batarya kurulum maliyeti TL/kWh")


class GridImpactRequest(BaseModel):
    region_id: str = Field("1-LV-rural1--1-sw", description="SimBench region identifier")
    pv_penetration_pct: float = Field(30.0, ge=0, le=200, description="PV penetration as % of total load")
    bess_penetration_pct: float = Field(0.0, ge=0, le=200, description="BESS penetration as % of total load")
    load_growth_pct: float = Field(0.0, ge=0, le=500, description="Load growth percentage from baseline")
    run_penetration_sweep: bool = Field(False, description="Also run hosting capacity analysis 0-100%")
    run_deferral_analysis: bool = Field(False, description="Also run transformer deferral analysis")
    deferral_years: int = Field(10, ge=1, le=30)
    annual_load_growth_pct: float = Field(3.0, ge=0, le=20)


class IncentiveModel(BaseModel):
    type: str = Field(..., description="Incentive type: capital_subsidy | tax_deduction | net_metering | feed_in_tariff | capacity_payment | low_interest_loan | vat_exemption | self_consumption_premium | carbon_credit")
    subsidy_pct: Optional[float] = None
    tax_deduction_pct: Optional[float] = None
    corporate_tax_rate: Optional[float] = None
    net_metering_ratio: Optional[float] = None
    fit_rate_tl_per_kwh: Optional[float] = None
    capacity_payment_tl_per_kw_yr: Optional[float] = None
    loan_pct: Optional[float] = None
    loan_rate_pct: Optional[float] = None
    loan_term_yr: Optional[int] = None
    market_rate_pct: Optional[float] = None
    vat_rate: Optional[float] = None
    premium_tl_per_kwh: Optional[float] = None
    carbon_credit_tl_per_ton: Optional[float] = None


class PolicyModel(BaseModel):
    name: str
    incentives: List[IncentiveModel]


class PolicyScenarioRequest(BaseModel):
    base_investment_tl: float = Field(..., gt=0, description="Base investment cost (TL)")
    annual_savings_tl: float = Field(..., gt=0, description="First-year annual savings (TL)")
    lifetime_years: int = Field(25, ge=1, le=40)
    discount_rate: float = Field(0.12, ge=0, le=1)
    policies: List[PolicyModel] = Field(..., min_length=1)
    context: Optional[dict] = Field(
        default=None,
        description="Simulation context: system_kw, annual_export_kwh, annual_production_kwh, etc."
    )


class MonteCarloRequest(BaseModel):
    base_investment_tl: float = Field(..., gt=0, description="Initial investment (TL)")
    base_annual_savings_tl: float = Field(..., gt=0, description="First-year annual savings (TL)")
    lifetime_years: int = Field(25, ge=1, le=40)
    base_discount_rate: float = Field(0.12, ge=0, le=1)
    n_iterations: int = Field(10000, ge=100, le=100000)
    parallel: bool = Field(True, description="Use multiprocessing")


@router.post("/pv", summary="PV Üretim Simülasyonu")
def simulate_pv(req: PVRequest):
    try:
        production = simulate_pv_production(
            req.latitude, req.longitude,
            req.panel_kw, req.tilt, req.azimuth
        )
        annual_kwh = float(production.sum())
        capacity_factor = annual_kwh / (req.panel_kw * 8760)
        monthly = [float(production[m * 730:(m + 1) * 730].sum()) for m in range(12)]

        return {
            "annual_production_kwh": round(annual_kwh, 2),
            "monthly_breakdown_kwh": [round(v, 2) for v in monthly],
            "capacity_factor": round(capacity_factor, 4),
            "peak_hour_kw": round(float(production.max()), 3),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pv-bess", summary="PV + BESS Fizibilite Analizi")
def simulate_pv_bess(req: PVBESSRequest):
    # Ortak fizibilite servisi — advisor endpoint'i ile aynı mantığı paylaşır (drift önlenir)
    try:
        return run_pv_bess(req)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/grid-impact", summary="Şebeke Etki Analizi (Newton-Raphson Yük Akışı)")
def simulate_grid(req: GridImpactRequest):
    """
    Runs Newton-Raphson load flow for PV/BESS grid impact assessment.
    Optionally performs hosting capacity sweep and transformer deferral analysis.
    """
    cache_params = req.model_dump()
    cached = get_cached(cache_params)
    if cached is not None:
        return cached

    try:
        result = simulate_grid_impact(
            region_id=req.region_id,
            pv_penetration_pct=req.pv_penetration_pct,
            bess_penetration_pct=req.bess_penetration_pct,
            load_growth_pct=req.load_growth_pct,
        )

        response = {"grid_impact": result}

        if req.run_penetration_sweep:
            df = run_penetration_analysis(region_id=req.region_id)
            response["hosting_capacity_analysis"] = {
                "hosting_capacity_pct": df.attrs.get("hosting_capacity_pct", 100.0),
                "sweep_results": df.to_dict(orient="records"),
            }

        if req.run_deferral_analysis:
            deferral = simulate_transformer_deferral(
                region_id=req.region_id,
                pv_penetration_pct=req.pv_penetration_pct,
                bess_penetration_pct=req.bess_penetration_pct,
                years=req.deferral_years,
                annual_load_growth_pct=req.annual_load_growth_pct,
            )
            response["transformer_deferral"] = deferral

        set_cached(cache_params, response)
        return response

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/policy-scenario", summary="Teşvik Politikası Senaryo Karşılaştırması")
def policy_scenario(req: PolicyScenarioRequest):
    """
    Compares multiple incentive policy packages on the same base investment.
    Returns NPV, IRR, payback, state cost, and effectiveness ranking.
    """
    cache_params = req.model_dump()
    cached = get_cached(cache_params)
    if cached is not None:
        return cached

    try:
        # Build base cashflows from investment and savings
        tariff_growth = 0.08
        base_cashflows = [-req.base_investment_tl] + [
            req.annual_savings_tl * (1 + tariff_growth) ** y
            for y in range(req.lifetime_years)
        ]

        # Convert Pydantic models to dicts for policy engine
        policies_dict = [p.model_dump(exclude_none=True) for p in req.policies]

        context = req.context or {}
        # Provide sensible defaults for context if not supplied
        context.setdefault("system_kw", 10.0)
        context.setdefault("annual_export_kwh", req.annual_savings_tl / 5.0)
        context.setdefault("annual_production_kwh", req.annual_savings_tl / 4.0)
        context.setdefault("annual_self_consumed_kwh", req.annual_savings_tl / 6.0)
        context.setdefault("base_rate_tl_per_kwh", 5.30)
        context.setdefault("current_export_rate", 5.30)
        context.setdefault("system_cost_pre_vat", req.base_investment_tl / 1.20)

        result = compare_policies(
            base_cashflows=base_cashflows,
            policies=policies_dict,
            context=context,
            discount_rate=req.discount_rate,
        )

        set_cached(cache_params, result)
        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/monte-carlo", summary="Monte Carlo Belirsizlik Analizi")
def monte_carlo_simulation(req: MonteCarloRequest):
    """
    Runs Monte Carlo simulation with 10,000 iterations.
    Returns NPV and payback period distributions with percentiles.
    """
    cache_params = req.model_dump()
    cached = get_cached(cache_params)
    if cached is not None:
        return cached

    try:
        result = run_monte_carlo(
            base_investment_tl=req.base_investment_tl,
            base_annual_savings_tl=req.base_annual_savings_tl,
            lifetime_years=req.lifetime_years,
            base_discount_rate=req.base_discount_rate,
            n_iterations=req.n_iterations,
            parallel=req.parallel,
        )

        set_cached(cache_params, result)
        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
