from __future__ import annotations

"""
Tests for Redis-backed session memory.
Tests run against the real Redis container.
Fallback (in-memory) mode tested via monkeypatching.
"""

import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.llm.memory.session_memory import SessionMemory, session_memory

client = TestClient(app)


def _uid() -> str:
    """Her test için benzersiz session ID üret."""
    return f"test_mem_{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# TestSessionMemoryRedis
# ---------------------------------------------------------------------------

class TestSessionMemoryRedis:
    """Gerçek Redis container'ına karşı çalışan testler."""

    def test_get_empty_session_returns_defaults(self):
        sid = _uid()
        try:
            data = session_memory.get_session(sid)
            assert data["stakeholder_type"] == "residential"
            assert data["location"] is None
            assert data["monthly_bill_tl"] is None
            assert data["existing_pv_kw"] is None
            assert data["previous_simulations"] == []
            assert data["chat_history"] == []
        finally:
            session_memory.delete_session(sid)

    def test_save_and_get_session(self):
        sid = _uid()
        try:
            payload = {
                "stakeholder_type": "commercial",
                "location": {"city": "ankara", "lat": 39.93, "lon": 32.86},
                "monthly_bill_tl": 5000.0,
                "existing_pv_kw": None,
                "previous_simulations": [],
                "chat_history": [],
            }
            session_memory.save_session(sid, payload)
            retrieved = session_memory.get_session(sid)
            assert retrieved["stakeholder_type"] == "commercial"
            assert retrieved["location"]["city"] == "ankara"
            assert retrieved["monthly_bill_tl"] == 5000.0
        finally:
            session_memory.delete_session(sid)

    def test_update_context_partial(self):
        sid = _uid()
        try:
            # İlk olarak commercial olarak kaydet
            session_memory.save_session(sid, {
                "stakeholder_type": "commercial",
                "location": None,
                "monthly_bill_tl": None,
                "existing_pv_kw": None,
                "previous_simulations": [],
                "chat_history": [],
            })
            # Sadece location güncelle
            session_memory.update_context(sid, location={"city": "izmir", "lat": 38.42, "lon": 27.14})
            updated = session_memory.get_session(sid)
            # stakeholder_type değişmemiş olmalı
            assert updated["stakeholder_type"] == "commercial"
            # location güncellendi
            assert updated["location"]["city"] == "izmir"
        finally:
            session_memory.delete_session(sid)

    def test_append_simulation_keeps_last_5(self):
        sid = _uid()
        try:
            for i in range(6):
                session_memory.append_simulation(sid, {"index": i, "npv": i * 1000})
            session = session_memory.get_session(sid)
            sims = session["previous_simulations"]
            assert len(sims) == 5
            # Son 5 simülasyon (index 1..5) kalmış olmalı
            assert sims[0]["index"] == 1
            assert sims[-1]["index"] == 5
        finally:
            session_memory.delete_session(sid)

    def test_save_chat_history_truncates_at_30(self):
        sid = _uid()
        try:
            messages = [{"role": "user", "content": f"msg {i}"} for i in range(35)]
            session_memory.save_chat_history(sid, messages)
            history = session_memory.get_chat_history(sid)
            assert len(history) == 30
            # Son 30 mesaj korundu (index 5..34)
            assert history[0]["content"] == "msg 5"
            assert history[-1]["content"] == "msg 34"
        finally:
            session_memory.delete_session(sid)

    def test_delete_session(self):
        sid = _uid()
        session_memory.save_session(sid, {
            "stakeholder_type": "municipal",
            "location": None,
            "monthly_bill_tl": None,
            "existing_pv_kw": None,
            "previous_simulations": [],
            "chat_history": [],
        })
        session_memory.delete_session(sid)
        # Silindikten sonra default dönmeli
        data = session_memory.get_session(sid)
        assert data["stakeholder_type"] == "residential"
        assert data["chat_history"] == []

    def test_list_active_sessions(self):
        sid1 = _uid()
        sid2 = _uid()
        try:
            session_memory.save_session(sid1, {
                "stakeholder_type": "residential",
                "location": None,
                "monthly_bill_tl": None,
                "existing_pv_kw": None,
                "previous_simulations": [],
                "chat_history": [],
            })
            session_memory.save_session(sid2, {
                "stakeholder_type": "utility",
                "location": None,
                "monthly_bill_tl": None,
                "existing_pv_kw": None,
                "previous_simulations": [],
                "chat_history": [],
            })
            active = session_memory.list_active_sessions()
            assert sid1 in active
            assert sid2 in active
        finally:
            session_memory.delete_session(sid1)
            session_memory.delete_session(sid2)


# ---------------------------------------------------------------------------
# TestSessionMemoryFallback
# ---------------------------------------------------------------------------

class TestSessionMemoryFallback:
    """Redis bağlantısı yokken in-memory fallback çalışmalı."""

    def test_fallback_mode_works(self, monkeypatch):
        import redis as redis_lib

        def _fail_from_url(*args, **kwargs):
            raise ConnectionError("Redis bağlanamıyor (mock)")

        monkeypatch.setattr(redis_lib, "from_url", _fail_from_url)

        mem = SessionMemory()
        assert mem._use_redis is False

        sid = _uid()
        # get → default
        data = mem.get_session(sid)
        assert data["stakeholder_type"] == "residential"

        # save → get
        data["stakeholder_type"] = "commercial"
        mem.save_session(sid, data)
        retrieved = mem.get_session(sid)
        assert retrieved["stakeholder_type"] == "commercial"

        # delete
        mem.delete_session(sid)
        assert mem.get_session(sid)["stakeholder_type"] == "residential"


# ---------------------------------------------------------------------------
# TestChatHistoryEndpoint
# ---------------------------------------------------------------------------

class TestChatHistoryEndpoint:
    """FastAPI endpoint'leri üzerinden chat history ve session delete testleri."""

    def test_history_endpoint_returns_messages(self):
        sid = _uid()
        try:
            # İki mesaj gönder (LLM_BACKEND=mock olduğu için hızlı)
            for msg in ["Merhaba", "Ankara için 10 kW PV analizi yap"]:
                r = client.post("/api/v1/chat/message", json={
                    "session_id": sid,
                    "message": msg,
                    "stakeholder_type": "residential",
                })
                assert r.status_code == 200

            # History endpoint'ini sorgula
            r = client.get(f"/api/v1/chat/{sid}/history")
            assert r.status_code == 200
            body = r.json()
            assert body["session_id"] == sid
            assert isinstance(body["messages"], list)
            assert len(body["messages"]) >= 2
            assert "context" in body
            assert body["context"]["stakeholder_type"] == "residential"
        finally:
            session_memory.delete_session(sid)

    def test_delete_session_endpoint(self):
        sid = _uid()
        # Önce bir mesaj gönder
        client.post("/api/v1/chat/message", json={
            "session_id": sid,
            "message": "Test mesajı",
            "stakeholder_type": "commercial",
        })

        # Sil
        r = client.delete(f"/api/v1/chat/{sid}")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert body["session_id"] == sid

        # Silindikten sonra history boş olmalı
        r = client.get(f"/api/v1/chat/{sid}/history")
        assert r.status_code == 200
        assert r.json()["messages"] == []
