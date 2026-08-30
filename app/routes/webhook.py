import json
import hmac
import logging
from datetime import datetime, timezone
from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.callbacks import notify_system

logger = logging.getLogger(__name__)

router = APIRouter()

NON_TEXT_REPLY = "Por enquanto eu só entendo mensagens de texto. Pode escrever sua dúvida?"


@dataclass
class Inbound:
    phone: str
    text: str | None


async def _raw_body(request: Request) -> bytes:
    return await request.body()


def parse_evolution_event(payload: dict) -> Inbound | None:
    if payload.get("event") != "messages.upsert":
        return None
    data = payload.get("data") or {}
    # Variante aninhada: data.message contém {key, message}
    if "key" not in data:
        inner = data.get("message")
        if isinstance(inner, dict) and "key" in inner:
            data = inner
    key = data.get("key") or {}
    remote_jid = key.get("remoteJid") or ""
    if not remote_jid.endswith("@s.whatsapp.net"):
        return None
    if key.get("fromMe"):
        return None
    phone = remote_jid.split("@")[0]
    content = data.get("message") or {}
    text = content.get("conversation") or (content.get("extendedTextMessage") or {}).get("text")
    return Inbound(phone=phone, text=text)


@router.post("/webhooks/whatsapp")
def whatsapp_webhook(
    request: Request,
    token: str = Query(default=""),
    body: bytes = Depends(_raw_body),
) -> dict:
    settings = request.app.state.settings
    if not hmac.compare_digest(token.encode(), settings.webhook_token.encode()):
        raise HTTPException(status_code=401, detail="token inválido")

    try:
        payload = json.loads(body or b"{}")
        if not isinstance(payload, dict):
            return {"status": "ignored"}
        inbound = parse_evolution_event(payload)
        if inbound is None:
            if payload.get("event") == "messages.upsert":
                logger.warning("payload não reconhecido; body=%r", body[:500])
            return {"status": "ignored"}
        if inbound.text is None:
            request.app.state.whatsapp_evolution.send_text(inbound.phone, NON_TEXT_REPLY)
            return {"status": "replied"}
        reply = request.app.state.engine.handle_message(inbound.phone, inbound.text)
        request.app.state.whatsapp_evolution.send_text(inbound.phone, reply)
        _avisar_sistema(settings, inbound.phone, inbound.text, reply)
        return {"status": "replied"}
    except Exception:
        logger.exception("erro ao processar webhook; body=%r", body[:500])
        return {"status": "error-logged"}


def _avisar_sistema(settings, phone: str, message: str, reply: str) -> None:
    """Notifica o sistema do cliente; nunca atrapalha a resposta ao cliente."""
    try:
        notify_system(settings, {
            "phone": phone,
            "message": message,
            "reply": reply,
            "received_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception:
        logger.exception("falha ao notificar o sistema do cliente")
