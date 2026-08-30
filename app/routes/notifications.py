import hmac
import json
import re

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, field_validator

from app.providers.base import VoiceProviderError

router = APIRouter()

_PHONE_RE = re.compile(r"^55\d{10,11}$")


class NotificationIn(BaseModel):
    phone: str
    voice_message: str
    context: str | None = None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        if not _PHONE_RE.match(value):
            raise ValueError(
                "telefone deve ser 55 + DDD + número, só dígitos (12 a 13 no total)"
            )
        return value

    @field_validator("voice_message")
    @classmethod
    def validate_voice_message(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("voice_message não pode ser vazio")
        return value


@router.post("/api/notifications", status_code=201)
def create_notification(
    body: NotificationIn,
    request: Request,
    x_api_key: str = Header(default=""),
) -> dict:
    settings = request.app.state.settings
    if not hmac.compare_digest(x_api_key.encode(), settings.api_key.encode()):
        raise HTTPException(status_code=401, detail="chave de API inválida")

    try:
        nvoip_response = request.app.state.nvoip.send_voice_torpedo(
            body.phone, body.voice_message
        )
    except VoiceProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    status = "dry_run" if nvoip_response.get("dry_run") else "sent"
    notification_id = request.app.state.db.save_notification(
        body.phone, body.voice_message, body.context, status, json.dumps(nvoip_response)
    )
    return {"id": notification_id, "status": status, "nvoip": nvoip_response}
