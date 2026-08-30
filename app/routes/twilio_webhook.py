import base64
import hashlib
import hmac
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from app.callbacks import notify_system

logger = logging.getLogger(__name__)

router = APIRouter()


def is_valid_signature(url: str, params: dict, token: str, signature: str) -> bool:
    """Assinatura do Twilio: HMAC-SHA1 da URL + parâmetros ordenados."""
    data = url + "".join(f"{k}{params[k]}" for k in sorted(params))
    expected = base64.b64encode(
        hmac.new(token.encode(), data.encode(), hashlib.sha1).digest()
    ).decode()
    return hmac.compare_digest(expected.encode(), signature.encode())


@router.post("/webhooks/twilio-whatsapp")
async def twilio_whatsapp_webhook(request: Request) -> dict:
    settings = request.app.state.settings
    form = dict(await request.form())
    signature = request.headers.get("X-Twilio-Signature", "")

    if not is_valid_signature(
        str(request.url), form, settings.twilio_auth_token, signature
    ):
        raise HTTPException(status_code=403, detail="assinatura inválida")

    try:
        phone = str(form.get("From", "")).replace("whatsapp:", "").lstrip("+")
        text = str(form.get("Body", "")).strip()
        if not phone or not text:
            return {"status": "ignored"}
        reply = request.app.state.engine.handle_message(phone, text)
        request.app.state.whatsapp_twilio.send_text(phone, reply)
        _avisar_sistema(settings, phone, text, reply)
        return {"status": "replied"}
    except Exception:
        logger.exception("erro ao processar webhook do Twilio; form=%r", form)
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
