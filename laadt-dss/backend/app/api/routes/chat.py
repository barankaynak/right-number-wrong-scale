from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import settings
from app.llm.mock.mock_llm import MockLLMOrchestrator
from app.llm.ollama_orchestrator import OllamaOrchestrator

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


def _get_orchestrator() -> OllamaOrchestrator | MockLLMOrchestrator:
    if settings.LLM_BACKEND == "ollama":
        return OllamaOrchestrator()
    return MockLLMOrchestrator()


# Module-level singleton
orchestrator = _get_orchestrator()


class ChatRequest(BaseModel):
    session_id: str
    message: str
    stakeholder_type: str = "residential"


@router.post("/message")
def chat_message(req: ChatRequest):
    from app.llm.memory.session_memory import session_memory

    result = orchestrator.process_message(
        req.message, req.session_id, req.stakeholder_type
    )

    # API katmanında her zaman history kaydet (hangi backend olursa olsun)
    history = session_memory.get_chat_history(req.session_id)
    history.append({"role": "user", "content": req.message})
    reply = result.get("reply", "")
    if reply:
        history.append({"role": "assistant", "content": reply})
    session_memory.save_chat_history(req.session_id, history)

    return result


@router.get("/{session_id}/history")
def get_chat_history(session_id: str):
    from app.llm.memory.session_memory import session_memory
    history = session_memory.get_chat_history(session_id)
    context = session_memory.get_session(session_id)
    return {
        "session_id": session_id,
        "messages": history,
        "context": {
            "stakeholder_type": context.get("stakeholder_type"),
            "location": context.get("location"),
            "previous_simulations_count": len(context.get("previous_simulations", [])),
        },
    }


@router.delete("/{session_id}")
def delete_session(session_id: str):
    from app.llm.memory.session_memory import session_memory
    session_memory.delete_session(session_id)
    return {"status": "ok", "session_id": session_id}
