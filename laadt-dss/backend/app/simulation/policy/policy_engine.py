"""
Policy scenario engine for energy investment incentive analysis.

Supports 9 incentive mechanisms:
1. Capital subsidy
2. Tax deduction
3. Net metering ratio
4. Feed-in tariff
5. Capacity payment
6. Low-interest loan
7. VAT exemption
8. Self-consumption premium
9. Carbon credit
"""

import numpy as np
from typing import Optional


def apply_capital_subsidy(
    base_cashflows: list,
    subsidy_pct: float
) -> list:
    """Reduces initial investment by subsidy percentage."""
    cf = list(base_cashflows)
    cf[0] = cf[0] * (1 - subsidy_pct / 100)
    return cf


def apply_tax_deduction(
    base_cashflows: list,
    tax_deduction_pct: float,
    corporate_tax_rate: float = 0.25
) -> list:
    """
    Allows deducting investment cost from taxable income.
    Effective benefit = investment × tax_deduction_pct × corporate_tax_rate
    """
    cf = list(base_cashflows)
    tax_benefit = abs(cf[0]) * (tax_deduction_pct / 100) * corporate_tax_rate
    cf[0] = cf[0] + tax_benefit
    return cf


def apply_net_metering(
    base_cashflows: list,
    net_metering_ratio: float,
    annual_export_kwh: float,
    base_rate_tl_per_kwh: float,
    current_ratio: float = 1.0
) -> list:
    """
    Adjusts cashflows for different net metering ratios.
    net_metering_ratio: 1.0 = 1:1, 0.5 = export worth half import
    """
    cf = list(base_cashflows)
    ratio_change = net_metering_ratio - current_ratio
    annual_benefit_change = annual_export_kwh * base_rate_tl_per_kwh * ratio_change

    for i in range(1, len(cf)):
        cf[i] = cf[i] + annual_benefit_change

    return cf


def apply_feed_in_tariff(
    base_cashflows: list,
    fit_rate_tl_per_kwh: float,
    annual_export_kwh: float,
    current_export_rate_tl_per_kwh: float
) -> list:
    """Replaces net metering with guaranteed feed-in tariff."""
    cf = list(base_cashflows)
    rate_diff = fit_rate_tl_per_kwh - current_export_rate_tl_per_kwh
    annual_extra_revenue = annual_export_kwh * rate_diff

    for i in range(1, len(cf)):
        cf[i] = cf[i] + annual_extra_revenue

    return cf


def apply_capacity_payment(
    base_cashflows: list,
    capacity_payment_tl_per_kw_yr: float,
    system_kw: float
) -> list:
    """Annual capacity payment for maintaining dispatchable capacity."""
    cf = list(base_cashflows)
    annual_payment = capacity_payment_tl_per_kw_yr * system_kw

    for i in range(1, len(cf)):
        cf[i] = cf[i] + annual_payment

    return cf


def apply_low_interest_loan(
    base_cashflows: list,
    loan_pct: float,
    loan_rate_pct: float,
    loan_term_yr: int,
    market_rate_pct: float = 30.0
) -> list:
    """
    Replaces part of upfront investment with subsidized loan.
    Effective benefit = reduced financing cost vs market rate.
    """
    cf = list(base_cashflows)
    loan_amount = abs(cf[0]) * (loan_pct / 100)

    # Annual payment at subsidized rate
    r_sub = loan_rate_pct / 100
    r_market = market_rate_pct / 100

    if r_sub > 0:
        annual_sub = loan_amount * r_sub / (1 - (1 + r_sub) ** (-loan_term_yr))
    else:
        annual_sub = loan_amount / loan_term_yr

    if r_market > 0:
        annual_market = loan_amount * r_market / (1 - (1 + r_market) ** (-loan_term_yr))
    else:
        annual_market = loan_amount / loan_term_yr

    annual_saving = annual_market - annual_sub

    # Reduce upfront cost by loan (financed)
    cf[0] = cf[0] + loan_amount

    # But add repayment schedule (loan payments reduce annual benefits)
    for i in range(1, min(loan_term_yr + 1, len(cf))):
        cf[i] = cf[i] - annual_sub

    return cf


def apply_vat_exemption(
    base_cashflows: list,
    system_cost_pre_vat: float,
    vat_rate: float = 0.20
) -> list:
    """VAT exemption on system purchase (reduces upfront cost)."""
    cf = list(base_cashflows)
    vat_saving = system_cost_pre_vat * vat_rate
    cf[0] = cf[0] + vat_saving
    return cf


def apply_self_consumption_premium(
    base_cashflows: list,
    premium_tl_per_kwh: float,
    annual_self_consumed_kwh: float
) -> list:
    """Additional payment per kWh of self-consumed solar energy."""
    cf = list(base_cashflows)
    annual_premium = premium_tl_per_kwh * annual_self_consumed_kwh

    for i in range(1, len(cf)):
        cf[i] = cf[i] + annual_premium

    return cf


def apply_carbon_credit(
    base_cashflows: list,
    carbon_credit_tl_per_ton: float,
    annual_production_kwh: float,
    grid_emission_factor_kg_per_kwh: float = 0.45  # Turkey average
) -> list:
    """Carbon credit revenue from avoided grid emissions."""
    cf = list(base_cashflows)
    annual_co2_tons = annual_production_kwh * grid_emission_factor_kg_per_kwh / 1000
    annual_credit_revenue = annual_co2_tons * carbon_credit_tl_per_ton

    for i in range(1, len(cf)):
        cf[i] = cf[i] + annual_credit_revenue

    return cf


def apply_incentive(base_cashflows: list, incentive: dict, context: dict = None) -> list:
    """
    Applies a single incentive mechanism to base cashflows.

    incentive dict keys: type (required) + mechanism-specific parameters
    context dict: simulation context (system_kw, annual_export_kwh, etc.)
    """
    if context is None:
        context = {}

    itype = incentive.get("type", "")
    cf = list(base_cashflows)

    if itype == "capital_subsidy":
        cf = apply_capital_subsidy(cf, incentive.get("subsidy_pct", 30))

    elif itype == "tax_deduction":
        # A27: oran ondalık (apply_tax_deduction 0.25 bekler; eski varsayılan 25'ti)
        cf = apply_tax_deduction(cf, incentive.get("tax_deduction_pct", 100),
                                  incentive.get("corporate_tax_rate", 0.25))

    elif itype == "net_metering":
        cf = apply_net_metering(
            cf,
            incentive.get("net_metering_ratio", 1.0),
            context.get("annual_export_kwh", 1000),
            context.get("base_rate_tl_per_kwh", 5.30),
        )

    elif itype == "feed_in_tariff":
        cf = apply_feed_in_tariff(
            cf,
            incentive.get("fit_rate_tl_per_kwh", 3.0),
            context.get("annual_export_kwh", 1000),
            context.get("current_export_rate", 5.30),
        )

    elif itype == "capacity_payment":
        cf = apply_capacity_payment(
            cf,
            incentive.get("capacity_payment_tl_per_kw_yr", 5000),
            context.get("system_kw", 10),
        )

    elif itype == "low_interest_loan":
        cf = apply_low_interest_loan(
            cf,
            incentive.get("loan_pct", 70),
            incentive.get("loan_rate_pct", 10),
            incentive.get("loan_term_yr", 10),
            incentive.get("market_rate_pct", 30),
        )

    elif itype == "vat_exemption":
        cf = apply_vat_exemption(
            cf,
            context.get("system_cost_pre_vat", abs(base_cashflows[0]) / 1.20),
            incentive.get("vat_rate", 0.20),
        )

    elif itype == "self_consumption_premium":
        cf = apply_self_consumption_premium(
            cf,
            incentive.get("premium_tl_per_kwh", 0.5),
            context.get("annual_self_consumed_kwh", 3000),
        )

    elif itype == "carbon_credit":
        cf = apply_carbon_credit(
            cf,
            incentive.get("carbon_credit_tl_per_ton", 500),
            context.get("annual_production_kwh", 12000),
        )

    return cf


def compare_policies(
    base_cashflows: list,
    policies: list,
    context: dict = None,
    discount_rate: float = 0.12,
    budget_tl: Optional[float] = None
) -> dict:
    """
    Compares multiple incentive packages on the same base investment.

    Each policy is a list of incentives to apply.
    Returns ranking and comparison metrics.
    """
    from app.simulation.economic.economic_engine import (
        calculate_npv, calculate_irr, calculate_payback_period
    )

    if context is None:
        context = {}

    results = []

    for policy in policies:
        cf = list(base_cashflows)
        policy_name = policy.get("name", "Unnamed")
        incentives = policy.get("incentives", [])

        # Calculate state cost (how much does this incentive cost the government)
        state_cost = 0.0

        for incentive in incentives:
            cf = apply_incentive(cf, incentive, context)

            # Estimate state cost per incentive type
            itype = incentive.get("type", "")
            if itype == "capital_subsidy":
                state_cost += abs(base_cashflows[0]) * incentive.get("subsidy_pct", 30) / 100
            elif itype == "vat_exemption":
                state_cost += context.get("system_cost_pre_vat", 200000) * incentive.get("vat_rate", 0.20)
            elif itype == "feed_in_tariff":
                annual_fit_cost = (
                    context.get("annual_export_kwh", 1000) *
                    max(0, incentive.get("fit_rate_tl_per_kwh", 3) - context.get("current_export_rate", 5.30))
                )
                state_cost += annual_fit_cost * len(cf)

        npv = calculate_npv(cf, discount_rate)
        irr = calculate_irr(cf)
        payback = calculate_payback_period(cf, discount_rate)

        # Triggered investment = amount of private investment mobilized per TL of state cost
        triggered_investment = abs(base_cashflows[0])
        state_cost_per_mw = (state_cost / (context.get("system_kw", 10) / 1000)) if context.get("system_kw", 10) > 0 else 0

        # CO2 reduction
        annual_co2_tons = (
            context.get("annual_production_kwh", 12000) * 0.45 / 1000  # 0.45 kg CO2/kWh Turkey
        )

        # Incentive effectiveness score (NPV per TL of state cost)
        effectiveness_score = npv / state_cost if state_cost > 0 else float('inf')

        results.append({
            "policy_name": policy_name,
            "npv_tl": round(npv, 2),
            "irr_pct": round(irr * 100, 2) if not np.isnan(irr) else None,
            "simple_payback_years": payback["simple"],
            "discounted_payback_years": payback["discounted"],
            "state_cost_tl": round(state_cost, 2),
            "state_cost_per_mw_tl": round(state_cost_per_mw, 2),
            "triggered_investment_tl": round(triggered_investment, 2),
            "annual_co2_reduction_tons": round(annual_co2_tons, 2),
            "incentive_effectiveness_score": round(effectiveness_score, 4) if effectiveness_score != float('inf') else None,
            "modified_cashflows": [round(v, 2) for v in cf],
        })

    # Sort by NPV descending
    results.sort(key=lambda x: x["npv_tl"], reverse=True)

    return {
        "base_cashflows": [round(v, 2) for v in base_cashflows],
        "discount_rate": discount_rate,
        "policy_results": results,
        "best_policy_by_npv": results[0]["policy_name"] if results else None,
        "best_policy_by_effectiveness": (
            max(results, key=lambda x: x["incentive_effectiveness_score"] or 0)["policy_name"]
            if results else None
        ),
    }
