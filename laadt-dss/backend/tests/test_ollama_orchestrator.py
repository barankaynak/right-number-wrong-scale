from __future__ import annotations

"""Tests for OllamaOrchestrator (Faz 3.3).

All Ollama HTTP calls and simulation endpoint calls are mocked —
no real network traffic is made during tests.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from app.llm.mock.mock_llm import MockLLMOrchestrator
from app.llm.ollama_orchestrator import CITY_COORDS, OllamaOrchestrator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_text_response(content: str) -> dict:
    """Build a minimal Ollama /api/chat message with plain text."""
    return {"role": "assistant", "content": content, "tool_calls": None}


def _make_tool_call_response(tool_name: str, arguments: dict) -> dict:
    """Build a minimal Ollama /api/chat message with a single tool_call."""
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "function": {
                    "name": tool_name,
                    "arguments": arguments,
                }
            }
        ],
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def orchestrator() -> OllamaOrchestrator:
    orch = OllamaOrchestrator()
    # Her testten önce bilinen test session'larını temizle (Redis + local)
    for sid in ("sess-hist", "sess-trunc", "test-sess", "sess-city", "sess-fallback", "sess-bill"):
        orch._memory.delete_session(sid)
    orch._memory._local.clear()
    return orch


# ---------------------------------------------------------------------------
# TestOllamaOrchestrator
# ---------------------------------------------------------------------------

class TestOllamaOrchestrator:

    def test_direct_text_response(self, orchestrator: OllamaOrchestrator) -> None:
        """Model returns plain text (no tool_call) → reply is set correctly."""
        expected_content = "Merhaba! Size yardımcı olabilirim."

        with patch("app.llm.ollama_orchestrator.httpx.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.raise_for_status.return_value = None
            mock_resp.json.return_value = {"message": _make_text_response(expected_content)}
            mock_post.return_value = mock_resp

            result = orchestrator.process_message("Merhaba", "sess-001")

        assert result["reply"] == expected_content
        assert result["simulation_result"] is None
        assert result["missing_params"] == []

    def test_tool_call_simulate_pv_bess(self, orchestrator: OllamaOrchestrator) -> None:
        """Model issues simulate_pv_bess tool_call → executed, then narrated."""
        sim_result = {
            "annual_savings_tl": 15000,
            "simple_payback_years": 8.5,
            "npv_tl": 120000,
            "irr_percent": 14.2,
        }
        narration = "Ankara için 10 kW sistem kurulumu önerilmektedir."

        first_response = _make_tool_call_response(
            "simulate_pv_bess", {"city": "ankara", "panel_kw": 10}
        )
        second_response = _make_text_response(narration)

        call_count = 0

        def _fake_post(url: str, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            mock_resp.raise_for_status.return_value = None
            if "/api/chat" in url:
                # First call → tool_call, second call → narration
                if call_count == 1:
                    mock_resp.json.return_value = {"message": first_response}
                else:
                    mock_resp.json.return_value = {"message": second_response}
            else:
                # Simulation endpoint call
                mock_resp.json.return_value = sim_result
            return mock_resp

        with patch("app.llm.ollama_orchestrator.httpx.post", side_effect=_fake_post):
            result = orchestrator.process_message(
                "Ankara'da 10 kW sistem fizibilitesi", "sess-002"
            )

        assert result["reply"] == narration
        assert result["simulation_result"] is not None
        assert result["simulation_result"]["npv_tl"] == 120000

    def test_city_coordinate_mapping(self, orchestrator: OllamaOrchestrator) -> None:
        """_execute_tool maps 'istanbul' to correct coordinates."""
        captured_payload: dict = {}

        def _fake_post(url: str, **kwargs):
            nonlocal captured_payload
            if "/pv-bess" in url:
                captured_payload = kwargs.get("json", {})
            mock_resp = MagicMock()
            mock_resp.raise_for_status.return_value = None
            mock_resp.json.return_value = {
                "annual_savings_tl": 12000,
                "simple_payback_years": 9.0,
                "npv_tl": 90000,
                "irr_percent": 12.5,
            }
            return mock_resp

        with patch("app.llm.ollama_orchestrator.httpx.post", side_effect=_fake_post):
            orchestrator._execute_tool(
                "simulate_pv_bess",
                {"city": "istanbul", "panel_kw": 5},
                "residential",
            )

        assert captured_payload.get("latitude") == pytest.approx(41.01)
        assert captured_payload.get("longitude") == pytest.approx(28.95)

    def test_session_history_grows(self, orchestrator: OllamaOrchestrator) -> None:
        """Each process_message call appends user + assistant entries to history."""
        with patch("app.llm.ollama_orchestrator.httpx.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.raise_for_status.return_value = None
            mock_resp.json.return_value = {
                "message": _make_text_response("Yanıt 1")
            }
            mock_post.return_value = mock_resp
            orchestrator.process_message("Mesaj 1", "sess-hist")

            mock_resp.json.return_value = {
                "message": _make_text_response("Yanıt 2")
            }
            orchestrator.process_message("Mesaj 2", "sess-hist")

        history = orchestrator._memory.get_chat_history("sess-hist")
        # 2 user + 2 assistant = 4 entries
        assert len(history) == 4
        assert history[0]["role"] == "user"
        assert history[1]["role"] == "assistant"
        assert history[2]["role"] == "user"
        assert history[3]["role"] == "assistant"

    def test_history_truncation(self, orchestrator: OllamaOrchestrator) -> None:
        """History is capped at 20 messages after exceeding the limit."""
        with patch("app.llm.ollama_orchestrator.httpx.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.raise_for_status.return_value = None
            mock_resp.json.return_value = {
                "message": _make_text_response("ok")
            }
            mock_post.return_value = mock_resp

            # 16 calls → 32 messages → truncated to 30 (SessionMemory cap)
            for i in range(16):
                orchestrator.process_message(f"msg {i}", "sess-trunc")

        assert len(orchestrator._memory.get_chat_history("sess-trunc")) == 30

    def test_fallback_on_ollama_error(self, orchestrator: OllamaOrchestrator) -> None:
        """ConnectError from Ollama triggers MockLLMOrchestrator fallback gracefully."""
        import httpx as _httpx

        with patch("app.llm.ollama_orchestrator.httpx.post") as mock_post:
            mock_post.side_effect = _httpx.ConnectError("connection refused")

            result = orchestrator.process_message(
                "Güneş paneli hakkında bilgi ver", "sess-fallback"
            )

        # MockOrchestrator always returns a reply (may be None sim but reply is str)
        assert isinstance(result["reply"], str)
        assert len(result["reply"]) > 0

    def _bill_payload(self, orchestrator: OllamaOrchestrator, monkeypatch, source: str) -> dict:
        monkeypatch.setenv("IRRADIANCE_SOURCE", source)
        captured_payload: dict = {}

        def _fake_post(url: str, **kwargs):
            nonlocal captured_payload
            if "/pv-bess" in url:
                captured_payload = kwargs.get("json", {})
            mock_resp = MagicMock()
            mock_resp.raise_for_status.return_value = None
            mock_resp.json.return_value = {"annual_savings_tl": 5000}
            return mock_resp

        with patch("app.llm.ollama_orchestrator.httpx.post", side_effect=_fake_post):
            orchestrator._execute_tool(
                "simulate_pv_bess",
                {"city": "ankara", "panel_kw": 5, "monthly_bill_tl": 1000},
                "residential",
            )
        return captured_payload

    def test_monthly_bill_conversion(self, orchestrator: OllamaOrchestrator, monkeypatch) -> None:
        """A27: monthly_bill_tl is inverted through the residential tiered tariff."""
        from app.simulation.advisor.sizing import bill_to_annual_consumption
        payload = self._bill_payload(orchestrator, monkeypatch, "pvgis_tmy_cache")
        expected = bill_to_annual_consumption(monthly_bill_tl=1000, stakeholder_type="residential")
        assert payload.get("annual_consumption_kwh") == pytest.approx(expected)
        assert 1500 < expected < 6000          # ~4 TL/kWh, not the old 0.5 TL/kWh

    def test_monthly_bill_conversion_july_replay(self, orchestrator: OllamaOrchestrator, monkeypatch) -> None:
        """A27: the July 2026 replay keeps the old fixed 0.5 TL/kWh conversion."""
        payload = self._bill_payload(orchestrator, monkeypatch, "clearsky")
        assert payload.get("annual_consumption_kwh") == pytest.approx(1000 * 12 / 0.5)


# ---------------------------------------------------------------------------
# TestOrchestratorSelection
# ---------------------------------------------------------------------------

class TestOrchestratorSelection:

    def test_ollama_backend_selected(self) -> None:
        """LLM_BACKEND='ollama' → _get_orchestrator returns OllamaOrchestrator."""
        from app.core.config import settings
        from app.api.routes.chat import _get_orchestrator

        original = settings.LLM_BACKEND
        try:
            settings.LLM_BACKEND = "ollama"
            orch = _get_orchestrator()
            assert isinstance(orch, OllamaOrchestrator)
        finally:
            settings.LLM_BACKEND = original

    def test_mock_backend_selected(self) -> None:
        """LLM_BACKEND='mock' → _get_orchestrator returns MockLLMOrchestrator."""
        from app.core.config import settings
        from app.api.routes.chat import _get_orchestrator

        original = settings.LLM_BACKEND
        try:
            settings.LLM_BACKEND = "mock"
            orch = _get_orchestrator()
            assert isinstance(orch, MockLLMOrchestrator)
        finally:
            settings.LLM_BACKEND = original
