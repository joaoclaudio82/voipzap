import base64
import hashlib
import hmac
import logging

from fastapi import APIRouter, HTTPException, Request

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
        request.app.state.evolution.send_text(phone, reply)
        return {"status": "replied"}
    except Exception:
        logger.exception("erro ao processar webhook do Twilio; form=%r", form)
        return {"status": "error-logged"}
