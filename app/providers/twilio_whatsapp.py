import logging

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)

_API = "https://api.twilio.com/2010-04-01"


class TwilioWhatsAppError(Exception):
    pass


class TwilioWhatsAppProvider:
    """Envia mensagens de WhatsApp pela API oficial do Twilio."""

    def __init__(self, settings: Settings, http: httpx.Client | None = None):
        self.settings = settings
        self.http = http or httpx.Client(timeout=30)

    def send_text(self, number: str, text: str) -> dict:
        if self.settings.dry_run:
            logger.info("[DRY_RUN] whatsapp (twilio) para %s: %r", number, text)
            return {"dry_run": True, "number": number, "text": text}

        if not (self.settings.twilio_account_sid and self.settings.twilio_auth_token):
            raise TwilioWhatsAppError(
                "credenciais Twilio ausentes: preencha TWILIO_ACCOUNT_SID e "
                "TWILIO_AUTH_TOKEN no .env"
            )

        url = f"{_API}/Accounts/{self.settings.twilio_account_sid}/Messages.json"
        form = {
            "To": _whatsapp(number),
            "From": _whatsapp(self.settings.twilio_whatsapp_from),
            "Body": text,
        }
        try:
            response = self.http.post(
                url,
                data=form,
                auth=(self.settings.twilio_account_sid, self.settings.twilio_auth_token),
            )
        except httpx.HTTPError as exc:
            raise TwilioWhatsAppError(f"falha de rede ao chamar o Twilio: {exc}") from exc
        if response.status_code >= 400:
            raise TwilioWhatsAppError(
                f"Twilio respondeu {response.status_code}: {response.text}"
            )
        return response.json()


def _whatsapp(number: str) -> str:
    if number.startswith("whatsapp:"):
        return number
    return f"whatsapp:{number if number.startswith('+') else '+' + number}"
