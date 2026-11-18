import pytest
from unittest.mock import patch, MagicMock
from app.llm.mock.mock_llm import MockLLMOrchestrator


@pytest.fixture
def orchestrator():
    return MockLLMOrchestrator()


def test_pv_intent_detection(orchestrator):
    intent = orchestrator._classify_intent("Ankara'da 10 kW GES kurmak istiyorum")
    assert intent == "pv_feasibility"


def test_bess_intent_detection(orchestrator):
    intent = orchestrator._classify_intent("14.4 kWh batarya taksam kaç yılda amorti eder?")
    assert intent == "bess_feasibility"


def test_savings_intent_detection(orchestrator):
    intent = orchestrator._classify_intent("aylık faturamda ne kadar tasarruf ederim?")
    assert intent == "savings_query"


def test_param_extraction_panel_kw(orchestrator):
    params = orchestrator._extract_params("10 kW panel kurmak istiyorum")
    assert params.get("panel_kw") == 10.0


def test_param_extraction_city(orchestrator):
    params = orchestrator._extract_params("Ankara'da bir sistem kuracağım")
    assert "latitude" in params
    assert abs(params["latitude"] - 39.93) < 0.1


def test_response_format(orchestrator):
    """Test that the response always has required keys."""
    # Mock the simulation call to return a sample result
    mock_result = {
        "annual_savings_tl": 15000,
        "simple_payback_years": 7.5,
        "discounted_payback_years": 9.2,
        "npv_tl": 80000,
        "irr_percent": 14.5,
        "self_consumption_ratio": 0.82,
        "annual_production_kwh": 14500,
        "total_grid_import_kwh": 1000,
        "total_grid_export_kwh": 2000,
        "system_cost_tl": 350000,
    }
    response = orchestrator._format_response(mock_result, "pv_feasibility", {"panel_kw": 10.0})
    assert "reply" in response
    assert "simulation_result" in response
    assert "missing_params" in response
    assert "follow_up_questions" in response
    assert "15.000" in response["reply"] or "15,000" in response["reply"]
