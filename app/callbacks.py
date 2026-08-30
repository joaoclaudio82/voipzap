"""Avisa o sistema do cliente quando alguém responde no WhatsApp.

O envio nunca interrompe o atendimento: se o sistema de destino estiver fora
do ar, a falha vai para o log e o cliente recebe a resposta do bot do mesmo
jeito.
"""

import hashlib
import hmac
import json
import logging

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)


def notify_system(settings: Settings, event: dict, http: httpx.Client | None = None) -> None:
    if not settings.callback_url:
        return

    corpo = json.dumps(event, ensure_ascii=False).encode()
    headers = {"Content-Type": "application/json"}
    if settings.callback_secret:
        headers["X-Signature"] = hmac.new(
            settings.callback_secret.encode(), corpo, hashlib.sha256
        ).hexdigest()

    cliente = http or httpx.Client(timeout=10)
    try:
        resposta = cliente.post(settings.callback_url, content=corpo, headers=headers)
        if resposta.status_code >= 400:
            logger.warning(
                "callback recusado pelo sistema de destino (%s): %s",
                resposta.status_code,
                resposta.text[:200],
            )
    except Exception:
        logger.exception("falha ao enviar callback para %s", settings.callback_url)
