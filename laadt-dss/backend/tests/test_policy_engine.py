"""
Tests for policy/policy_engine.py — incentive mechanism and policy comparison.
"""
import pytest
import numpy as np
from unittest.mock import patch

from app.simulation.policy.policy_engine import (
    apply_capital_subsidy,
    apply_tax_deduction,
    apply_net_metering,
    apply_feed_in_tariff,
    apply_capacity_payment,
    apply_low_interest_loan,
    apply_vat_exemption,
    apply_self_consumption_premium,
    apply_carbon_credit,
    apply_incentive,
    compare_policies,
)


BASE_CF = [-200_000] + [25_000] * 25  # 200k investment, 25k/yr savings, 25 years


class TestApplyCapitalSubsidy:
    def test_reduces_initial_investment(self):
        cf = apply_capital_subsidy(BASE_CF, 30)
        assert cf[0] == pytest.approx(-200_000 * 0.70)

    def test_does_not_change_annual_cashflows(self):
        cf = apply_capital_subsidy(BASE_CF, 30)
        assert cf[1:] == BASE_CF[1:]

    def test_zero_subsidy_no_change(self):
        cf = apply_capital_subsidy(BASE_CF, 0)
        assert cf[0] == BASE_CF[0]

    def test_100_percent_subsidy_zero_investment(self):
        cf = apply_capital_subsidy(BASE_CF, 100)
        assert cf[0] == pytest.approx(0.0)

    def test_does_not_mutate_original(self):
        original = list(BASE_CF)
        apply_capital_subsidy(BASE_CF, 30)
        assert BASE_CF == original


class TestApplyTaxDeduction:
    def test_reduces_initial_investment(self):
        cf = apply_tax_deduction(BASE_CF, 100, 0.25)
        expected_benefit = 200_000 * 1.0 * 0.25
        assert cf[0] == pytest.approx(BASE_CF[0] + expected_benefit)

    def test_partial_deduction(self):
        cf = apply_tax_deduction(BASE_CF, 50, 0.25)
        expected_benefit = 200_000 * 0.50 * 0.25
        assert cf[0] == pytest.approx(BASE_CF[0] + expected_benefit)


class TestApplyNetMetering:
    def test_higher_ratio_increases_annual_cashflows(self):
        cf_base = apply_net_metering(BASE_CF, 1.0, 5000, 5.30, current_ratio=1.0)
        cf_better = apply_net_metering(BASE_CF, 1.5, 5000, 5.30, current_ratio=1.0)
        for i in range(1, len(BASE_CF)):
            assert cf_better[i] > cf_base[i]

    def test_no_change_when_ratio_unchanged(self):
        cf = apply_net_metering(BASE_CF, 1.0, 5000, 5.30, current_ratio=1.0)
        assert cf[1:] == BASE_CF[1:]


class TestApplyFeedInTariff:
    def test_higher_fit_increases_revenue(self):
        cf_low = apply_feed_in_tariff(BASE_CF, 3.0, 10000, 2.0)
        cf_high = apply_feed_in_tariff(BASE_CF, 6.0, 10000, 2.0)
        assert cf_high[1] > cf_low[1]

    def test_lower_fit_than_current_reduces_revenue(self):
        cf = apply_feed_in_tariff(BASE_CF, 1.0, 10000, 5.30)
        assert cf[1] < BASE_CF[1]


class TestApplyCapacityPayment:
    def test_annual_payment_added(self):
        cf = apply_capacity_payment(BASE_CF, 5000, 10)  # 5000 TL/kW/yr, 10 kW
        expected_extra = 5000 * 10  # = 50,000 TL/yr
        for i in range(1, len(cf)):
            assert cf[i] == pytest.approx(BASE_CF[i] + expected_extra)

    def test_investment_unchanged(self):
        cf = apply_capacity_payment(BASE_CF, 5000, 10)
        assert cf[0] == BASE_CF[0]


class TestApplyLowInterestLoan:
    def test_reduces_upfront_cost(self):
        cf = apply_low_interest_loan(BASE_CF, 70, 10, 10, 30)
        loan_amount = 200_000 * 0.70
        assert cf[0] == pytest.approx(BASE_CF[0] + loan_amount)

    def test_repayments_reduce_annual_cashflows(self):
        cf = apply_low_interest_loan(BASE_CF, 70, 10, 10, 30)
        # Annual repayments should reduce years 1-10
        for i in range(1, 11):
            assert cf[i] < BASE_CF[i]

    def test_after_loan_term_cashflows_unchanged(self):
        cf = apply_low_interest_loan(BASE_CF, 70, 10, 10, 30)
        # Years 11+ should be same as base (no more repayments)
        for i in range(11, len(BASE_CF)):
            assert cf[i] == pytest.approx(BASE_CF[i])


class TestApplyVatExemption:
    def test_vat_saving_reduces_investment(self):
        system_pre_vat = 166_667  # ~200k with 20% VAT
        cf = apply_vat_exemption(BASE_CF, system_pre_vat, 0.20)
        vat_saving = system_pre_vat * 0.20
        assert cf[0] == pytest.approx(BASE_CF[0] + vat_saving)

    def test_annual_cashflows_unchanged(self):
        cf = apply_vat_exemption(BASE_CF, 166_667, 0.20)
        assert cf[1:] == BASE_CF[1:]


class TestApplySelfConsumptionPremium:
    def test_premium_added_to_annual_cashflows(self):
        cf = apply_self_consumption_premium(BASE_CF, 0.5, 10000)
        extra = 0.5 * 10000  # = 5000 TL/yr
        for i in range(1, len(cf)):
            assert cf[i] == pytest.approx(BASE_CF[i] + extra)


class TestApplyCarbonCredit:
    def test_credit_revenue_added(self):
        # 12000 kWh * 0.45 kg/kWh / 1000 = 5.4 tons * 500 TL/ton = 2700 TL/yr
        cf = apply_carbon_credit(BASE_CF, 500, 12000, 0.45)
        expected = 12000 * 0.45 / 1000 * 500
        for i in range(1, len(cf)):
            assert cf[i] == pytest.approx(BASE_CF[i] + expected)

    def test_investment_unchanged(self):
        cf = apply_carbon_credit(BASE_CF, 500, 12000)
        assert cf[0] == BASE_CF[0]


class TestApplyIncentive:
    def test_capital_subsidy_dispatch(self):
        incentive = {"type": "capital_subsidy", "subsidy_pct": 25}
        cf = apply_incentive(BASE_CF, incentive)
        assert cf[0] == pytest.approx(-200_000 * 0.75)

    def test_unknown_type_returns_unchanged(self):
        incentive = {"type": "nonexistent_incentive"}
        cf = apply_incentive(BASE_CF, incentive)
        assert cf == BASE_CF

    def test_context_used_for_capacity_payment(self):
        incentive = {"type": "capacity_payment", "capacity_payment_tl_per_kw_yr": 1000}
        context = {"system_kw": 50}
        cf = apply_incentive(BASE_CF, incentive, context)
        extra = 1000 * 50
        assert cf[1] == pytest.approx(BASE_CF[1] + extra)

    def test_none_context_uses_defaults(self):
        incentive = {"type": "carbon_credit", "carbon_credit_tl_per_ton": 500}
        cf = apply_incentive(BASE_CF, incentive, context=None)
        assert cf[1] > BASE_CF[1]  # Some revenue added


class TestComparePolicies:
    POLICIES = [
        {
            "name": "No Incentive",
            "incentives": []
        },
        {
            "name": "Capital Subsidy 30%",
            "incentives": [{"type": "capital_subsidy", "subsidy_pct": 30}]
        },
        {
            "name": "Carbon Credit",
            "incentives": [{"type": "carbon_credit", "carbon_credit_tl_per_ton": 500}]
        },
    ]

    def _mock_economic_engine(self):
        """Patch economic engine to return predictable values."""
        from app.simulation.economic import economic_engine
        return economic_engine

    def test_returns_policy_results_list(self):
        result = compare_policies(BASE_CF, self.POLICIES)
        assert "policy_results" in result
        assert len(result["policy_results"]) == 3

    def test_sorted_by_npv_descending(self):
        result = compare_policies(BASE_CF, self.POLICIES)
        npvs = [r["npv_tl"] for r in result["policy_results"]]
        assert npvs == sorted(npvs, reverse=True)

    def test_best_policy_by_npv_key(self):
        result = compare_policies(BASE_CF, self.POLICIES)
        assert "best_policy_by_npv" in result
        assert isinstance(result["best_policy_by_npv"], str)

    def test_state_cost_for_no_incentive_is_zero(self):
        result = compare_policies(BASE_CF, self.POLICIES)
        no_incentive = next(r for r in result["policy_results"] if r["policy_name"] == "No Incentive")
        assert no_incentive["state_cost_tl"] == 0.0

    def test_capital_subsidy_has_positive_state_cost(self):
        result = compare_policies(BASE_CF, self.POLICIES)
        subsidy = next(r for r in result["policy_results"] if r["policy_name"] == "Capital Subsidy 30%")
        assert subsidy["state_cost_tl"] > 0.0

    def test_result_contains_base_cashflows(self):
        result = compare_policies(BASE_CF, self.POLICIES)
        assert "base_cashflows" in result
        assert result["base_cashflows"][0] == pytest.approx(BASE_CF[0])

    def test_empty_policies_returns_empty_results(self):
        result = compare_policies(BASE_CF, [])
        assert result["policy_results"] == []
        assert result["best_policy_by_npv"] is None
