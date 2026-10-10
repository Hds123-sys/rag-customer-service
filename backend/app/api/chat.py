"""
智能问答API路由

会话历史按 session_id 保存在服务端内存中, 并设置 TTL 与数量上限, 防止内存无限增长。
"""
import logging
import threading
import time
import uuid
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user
from app.core.config import settings
from app.models.schemas import ChatRequest, ChatResponse, MessageResponse, SourceItem
from app.models.user import User
from app.services.rag import rag_service

logger = logging.getLogger(__name__)

router = APIRouter()

_MAX_SESSIONS = 500
_MAX_HISTORY_ITEMS = 50

_sessions: Dict[str, dict] = {}
_sessions_lock = threading.Lock()


def _prune_sessions() -> None:
    now = time.time()
    ttl = max(60, settings.CHAT_SESSION_TTL)
    with _sessions_lock:
        expired = [sid for sid, item in _sessions.items() if now - item["updated_at"] > ttl]
        for sid in expired:
            _sessions.pop(sid, None)
        if len(_sessions) > _MAX_SESSIONS:
            ordered = sorted(_sessions.items(), key=lambda kv: kv[1]["updated_at"])
            for sid, _ in ordered[: len(_sessions) - _MAX_SESSIONS]:
                _sessions.pop(sid, None)


def _get_history(session_id: str) -> List[dict]:
    with _sessions_lock:
        item = _sessions.get(session_id)
        return list(item["history"]) if item else []


def _append_history(session_id: str, role: str, content: str) -> None:
    with _sessions_lock:
        item = _sessions.setdefault(session_id, {"history": [], "updated_at": time.time()})
        item["history"].append({"role": role, "content": content})
        if len(item["history"]) > _MAX_HISTORY_ITEMS:
            item["history"] = item["history"][-_MAX_HISTORY_ITEMS:]
        item["updated_at"] = time.time()


def _clear_session(session_id: str) -> bool:
    with _sessions_lock:
        return _sessions.pop(session_id, None) is not None


@router.post("", response_model=ChatResponse, summary="智能问答")
@router.post("/", response_model=ChatResponse, include_in_schema=False)
def chat(request: ChatRequest, current_user: User = Depends(get_current_user)):
    _prune_sessions()

    session_id = request.session_id or str(uuid.uuid4())

    # 优先使用服务端会话历史, 否则回退到客户端上送的历史
    history: List[dict] = _get_history(session_id)
    if not history and request.chat_history:
        for item in request.chat_history:
            role = item.get("role")
            content = (item.get("content") or "").strip() if isinstance(item, dict) else ""
            if role in ("user", "assistant") and content:
                history.append({"role": role, "content": content})

    try:
        result = rag_service.chat(request.message, history)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("问答失败")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"问答失败: {exc}"
        ) from exc

    _append_history(session_id, "user", request.message)
    _append_history(session_id, "assistant", result["answer"])

    return ChatResponse(
        answer=result["answer"],
        sources=[SourceItem(**item) for item in result.get("sources", [])],
        session_id=session_id,
    )


@router.get("/history/{session_id}", summary="获取会话历史")
def get_chat_history(session_id: str, current_user: User = Depends(get_current_user)):
    return {"session_id": session_id, "history": _get_history(session_id)}


@router.delete("/history", response_model=MessageResponse, summary="清空所有会话历史")
def clear_all_history(current_user: User = Depends(get_current_user)):
    with _sessions_lock:
        _sessions.clear()
    return MessageResponse(message="所有对话历史已清空")


@router.delete("/history/{session_id}", response_model=MessageResponse, summary="清空指定会话历史")
def clear_chat_history(session_id: str, current_user: User = Depends(get_current_user)):
    existed = _clear_session(session_id)
    return MessageResponse(message="对话历史已清空" if existed else "会话不存在")