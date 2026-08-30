"""Consultas que outro sistema faz sobre avisos e conversas."""

import hmac
import json
import logging

from fastapi import APIRouter, Header, HTTPException, Query, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()


class CallStatus(BaseModel):
    status: str
    duration: int | None = None
    answered: bool | None = None


class NotificationOut(BaseModel):
    id: int
    phone: str
    voice_message: str
    context: str | None = None
    status: str
    created_at: str
    call: CallStatus | None = None


class MessageOut(BaseModel):
    direction: str
    text: str
    created_at: str


class ConversationOut(BaseModel):
    phone: str
    messages: list[MessageOut]


def require_api_key(request: Request, x_api_key: str) -> None:
    settings = request.app.state.settings
    if not hmac.compare_digest(x_api_key.encode(), settings.api_key.encode()):
        raise HTTPException(status_code=401, detail="chave de API inválida")


@router.get("/api/notifications/{notification_id}", response_model=NotificationOut)
def get_notification(
    notification_id: int, request: Request, x_api_key: str = Header(default="")
) -> NotificationOut:
    require_api_key(request, x_api_key)

    row = request.app.state.db.notification(notification_id)
    if row is None:
        raise HTTPException(status_code=404, detail="aviso não encontrado")

    return NotificationOut(
        **{k: row[k] for k in ("id", "phone", "voice_message", "context", "status", "created_at")},
        call=_call_status(request, row),
    )


def _call_status(request: Request, row: dict) -> CallStatus | None:
    """Desfecho da ligação, consultado no provedor — só ele sabe se atendeu."""
    provider = request.app.state.nvoip
    consultar = getattr(provider, "call_status", None)
    if consultar is None:
        return None
    try:
        sid = (json.loads(row["nvoip_response"] or "{}") or {}).get("sid")
    except (ValueError, TypeError):
        return None
    if not sid:
        return None
    try:
        return CallStatus(**consultar(sid))
    except Exception:
        logger.exception("falha ao consultar o status da chamada %s", sid)
        return None


@router.get("/api/conversations/{phone}", response_model=ConversationOut)
def get_conversation(
    phone: str,
    request: Request,
    limit: int = Query(default=50, ge=1, le=500),
    x_api_key: str = Header(default=""),
) -> ConversationOut:
    require_api_key(request, x_api_key)
    rows = request.app.state.db.recent_messages(phone, limit=limit)
    return ConversationOut(
        phone=phone,
        messages=[MessageOut(**{k: r[k] for k in ("direction", "text", "created_at")}) for r in rows],
    )
