from __future__ import annotations

"""
Redis-backed session memory for the LLM orchestrator.

Her oturum için saklanır (TTL: 24 saat):
  - stakeholder_type     : str  ("residential" / "commercial" / "municipal" / "utility")
  - location             : dict {"city": str, "lat": float, "lon": float} | None
  - monthly_bill_tl      : float | None
  - existing_pv_kw       : float | None  (varsa kurulu GES)
  - previous_simulations : list[dict]    (son 5 simülasyon sonucu, karşılaştırma için)
  - chat_history         : list[dict]    ({role, content} mesaj listesi, son 30 mesaj)

Fallback: Redis erişilemezse in-memory dict kullanır (warning logla).
"""

import json
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


class SessionMemory:
    SESSION_TTL = 86400  # 24 saat

    def __init__(self) -> None:
        self._redis = None
        self._local: dict[str, dict] = {}  # fallback
        self._use_redis = False
        self._connect()

    def _connect(self) -> None:
        try:
            import redis

            r = redis.from_url(settings.REDIS_URL, decode_responses=True)
            r.ping()
            self._redis = r
            self._use_redis = True
            logger.info("SessionMemory: Redis bağlantısı başarılı (%s)", settings.REDIS_URL)
        except Exception as exc:
            logger.warning(
                "SessionMemory: Redis bağlantısı kurulamadı (%s) — in-memory fallback kullanılıyor.",
                exc,
            )
            self._use_redis = False

    def _key(self, session_id: str) -> str:
        return f"laadt:session:{session_id}"

    def get_session(self, session_id: str) -> dict:
        """Mevcut session'ı döndür. Yoksa boş default dict oluştur."""
        default: dict = {
            "stakeholder_type": "residential",
            "location": None,
            "monthly_bill_tl": None,
            "existing_pv_kw": None,
            "previous_simulations": [],
            "chat_history": [],
        }
        if self._use_redis:
            try:
                raw = self._redis.get(self._key(session_id))
                if raw is None:
                    return default.copy()
                return json.loads(raw)
            except Exception as exc:
                logger.warning("SessionMemory.get_session Redis hatası: %s", exc)
                return default.copy()
        return self._local.get(session_id, default.copy())

    def save_session(self, session_id: str, data: dict) -> None:
        """Session'ı kaydet, TTL'i yenile."""
        if self._use_redis:
            try:
                self._redis.set(self._key(session_id), json.dumps(data, ensure_ascii=False), ex=self.SESSION_TTL)
                return
            except Exception as exc:
                logger.warning("SessionMemory.save_session Redis hatası: %s", exc)
        self._local[session_id] = data

    def update_context(self, session_id: str, **kwargs) -> None:
        """Belirli context alanlarını güncelle (location, stakeholder_type vb.)"""
        session = self.get_session(session_id)
        for k, v in kwargs.items():
            if k in session:
                session[k] = v
        self.save_session(session_id, session)

    def append_simulation(self, session_id: str, sim_result: dict) -> None:
        """Simülasyon sonucunu kaydet, son 5'i tut."""
        session = self.get_session(session_id)
        sims = session.get("previous_simulations", [])
        sims.append(sim_result)
        session["previous_simulations"] = sims[-5:]
        self.save_session(session_id, session)

    def get_provenance(self, session_id: str) -> list[dict]:
        """GFP provenance kayıtları (A1-r1: oturum-kalıcı graf)."""
        return self.get_session(session_id).get("provenance_records", [])

    def save_provenance(self, session_id: str, records: list[dict]) -> None:
        """Provenance kayıtlarını kaydet (üst sınır grafın kendisinde uygulanır)."""
        session = self.get_session(session_id)
        session["provenance_records"] = records
        self.save_session(session_id, session)

    def get_chat_history(self, session_id: str) -> list[dict]:
        """Chat geçmişini döndür."""
        return self.get_session(session_id).get("chat_history", [])

    def save_chat_history(self, session_id: str, history: list[dict]) -> None:
        """Chat geçmişini kaydet, son 30 mesajla sınırla."""
        session = self.get_session(session_id)
        session["chat_history"] = history[-30:]
        self.save_session(session_id, session)

    def delete_session(self, session_id: str) -> None:
        """Session'ı sil."""
        if self._use_redis:
            try:
                self._redis.delete(self._key(session_id))
                return
            except Exception as exc:
                logger.warning("SessionMemory.delete_session Redis hatası: %s", exc)
        self._local.pop(session_id, None)

    def list_active_sessions(self) -> list[str]:
        """Aktif session ID'lerini döndür (sadece Redis modda anlamlı)."""
        if self._use_redis:
            try:
                keys = self._redis.keys("laadt:session:*")
                return [k.replace("laadt:session:", "") for k in keys]
            except Exception as exc:
                logger.warning("SessionMemory.list_active_sessions Redis hatası: %s", exc)
                return []
        return list(self._local.keys())


# Module-level singleton
session_memory = SessionMemory()
