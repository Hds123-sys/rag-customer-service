"""
智能问答API路由

会话历史按 session_id 保存在服务端内存中, 并设置 TTL 与数量上限, 防止内存无限增长。
每个会话都绑定创建它的用户, 读取/清空时校验归属, 避免越权访问他人对话。
"""
import logging
import threading
import time
import uuid
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.ratelimit import enforce
from app.models.schemas import ChatRequest, ChatResponse, MessageResponse, SourceItem
from app.models.user import User
from app.services.rag import rag_service

logger = logging.getLogger(__name__)

router = APIRouter()

_MAX_SESSIONS = 500
_MAX_HISTORY_ITEMS = 50

# session_id -> {"user_id": int, "history": [...], "updated_at": float}
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


def _session_owner(session_id: str) -> Optional[int]:
    """返回会话归属用户 ID; 会话不存在时返回 None"""
    with _sessions_lock:
        item = _sessions.get(session_id)
        return item.get("user_id") if item else None


def _get_history(session_id: str, user_id: int) -> List[dict]:
    with _sessions_lock:
        item = _sessions.get(session_id)
        if not item or item.get("user_id") != user_id:
            return []
        return list(item["history"])


def _append_history(
    session_id: str,
    user_id: int,
    role: str,
    content: str,
    sources: Optional[List[dict]] = None,
) -> None:
    with _sessions_lock:
        item = _sessions.get(session_id)
        if not item or item.get("user_id") != user_id:
            item = {"user_id": user_id, "history": [], "updated_at": time.time()}
            _sessions[session_id] = item
        entry: dict = {"role": role, "content": content}
        if sources:
            # 一并保存来源, 便于前端刷新后仍能展示「参考来源」
            entry["sources"] = sources
        item["history"].append(entry)
        if len(item["history"]) > _MAX_HISTORY_ITEMS:
            item["history"] = item["history"][-_MAX_HISTORY_ITEMS:]
        item["updated_at"] = time.time()


def _clear_session(session_id: str, user_id: int) -> bool:
    with _sessions_lock:
        item = _sessions.get(session_id)
        if not item or item.get("user_id") != user_id:
            return False
        _sessions.pop(session_id, None)
        return True


@router.post("", response_model=ChatResponse, summary="智能问答")
@router.post("/", response_model=ChatResponse, include_in_schema=False)
def chat(
    request: ChatRequest,
    http_request: Request,
    current_user: User = Depends(get_current_user),
):
    _prune_sessions()
    enforce(http_request, "chat:ask", settings.RATE_LIMIT_CHAT, identifier=str(current_user.id))

    session_id = (request.session_id or "").strip() or str(uuid.uuid4())
    owner = _session_owner(session_id)
    if owner is not None and owner != current_user.id:
        # 该会话属于其他用户: 忽略客户端上送的 ID, 另开会话, 避免越权读写
        logger.warning("用户 %s 试图使用他人会话 %s, 已另开会话", current_user.id, session_id)
        session_id = str(uuid.uuid4())

    # 优先使用服务端会话历史, 否则回退到客户端上送的历史
    history: List[dict] = _get_history(session_id, current_user.id)
    if not history and request.chat_history:
        for item in request.chat_history:
            role = item.get("role")
            content = (item.get("content") or "").strip() if isinstance(item, dict) else ""
            if role in ("user", "assistant") and content:
                history.append({"role": role, "content": content})

    try:
        result = rag_service.chat(request.message, history, owner_id=current_user.id)
    except RuntimeError:
        logger.exception("问答服务不可用")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="问答服务暂时不可用，请稍后重试",
        ) from None
    except Exception:  # noqa: BLE001
        logger.exception("问答失败")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="问答失败，请稍后重试",
        ) from None

    _append_history(session_id, current_user.id, "user", request.message)
    _append_history(
        session_id,
        current_user.id,
        "assistant",
        result["answer"],
        result.get("sources", []),
    )

    return ChatResponse(
        answer=result["answer"],
        sources=[SourceItem(**item) for item in result.get("sources", [])],
        session_id=session_id,
    )


@router.get("/history/{session_id}", summary="获取会话历史")
def get_chat_history(session_id: str, current_user: User = Depends(get_current_user)):
    return {
        "session_id": session_id,
        "history": _get_history(session_id, current_user.id),
    }


@router.delete("/history", response_model=MessageResponse, summary="清空所有会话历史")
def clear_all_history(current_user: User = Depends(get_current_user)):
    with _sessions_lock:
        mine = [sid for sid, item in _sessions.items() if item.get("user_id") == current_user.id]
        for sid in mine:
            _sessions.pop(sid, None)
    return MessageResponse(message="所有对话历史已清空")


@router.delete("/history/{session_id}", response_model=MessageResponse, summary="清空指定会话历史")
def clear_chat_history(session_id: str, current_user: User = Depends(get_current_user)):
    existed = _clear_session(session_id, current_user.id)
    return MessageResponse(message="对话历史已清空" if existed else "会话不存在")