import logging
from xml.sax.saxutils import escape

import httpx

from app.config import Settings
from app.providers.base import VoiceProviderError

logger = logging.getLogger(__name__)

_API = "https://api.twilio.com/2010-04-01"


class TwilioError(VoiceProviderError):
    pass


class TwilioProvider:
    """Liga para o cliente e fala a mensagem com a voz TTS do Twilio."""

    def __init__(self, settings: Settings, http: httpx.Client | None = None):
        self.settings = settings
        self.http = http or httpx.Client(timeout=30)

    def send_voice_torpedo(self, called: str, message: str) -> dict:
        if self.settings.dry_run:
            logger.info("[DRY_RUN] ligação Twilio para %s: %r", called, message)
            return {"dry_run": True, "called": called, "message": message}

        if not (self.settings.twilio_account_sid and self.settings.twilio_auth_token):
            raise TwilioError(
                "credenciais Twilio ausentes: preencha TWILIO_ACCOUNT_SID e "
                "TWILIO_AUTH_TOKEN no .env"
            )

        url = f"{_API}/Accounts/{self.settings.twilio_account_sid}/Calls.json"
        form = {
            "To": _e164(called),
            "From": _e164(self.settings.twilio_caller),
            "Twiml": self._twiml(message),
        }
        try:
            response = self.http.post(
                url,
                data=form,
                auth=(self.settings.twilio_account_sid, self.settings.twilio_auth_token),
            )
        except httpx.HTTPError as exc:
            raise TwilioError(f"falha de rede ao chamar o Twilio: {exc}") from exc
        if response.status_code >= 400:
            raise TwilioError(f"Twilio respondeu {response.status_code}: {response.text}")
        return response.json()

    def call_status(self, call_sid: str) -> dict:
        """Desfecho da ligação — só o provedor sabe se o cliente atendeu."""
        if self.settings.dry_run:
            return {"status": "dry_run", "duration": None, "answered": None}

        url = f"{_API}/Accounts/{self.settings.twilio_account_sid}/Calls/{call_sid}.json"
        response = self.http.get(
            url, auth=(self.settings.twilio_account_sid, self.settings.twilio_auth_token)
        )
        if response.status_code >= 400:
            raise TwilioError(f"Twilio respondeu {response.status_code}: {response.text}")
        dados = response.json()
        status = dados.get("status") or "unknown"
        duracao = dados.get("duration")
        return {
            "status": status,
            "duration": int(duracao) if duracao not in (None, "") else None,
            "answered": status in {"completed", "in-progress"},
        }

    def _twiml(self, message: str) -> str:
        # A mensagem é falada duas vezes: quem atende costuma perder o começo.
        say = (
            f'<Say voice="{self.settings.twilio_voice}" language="pt-BR">'
            f"{escape(message)}</Say>"
        )
        return f'<Response><Pause length="1"/>{say}<Pause length="1"/>{say}</Response>'


def _e164(number: str) -> str:
    return number if number.startswith("+") else f"+{number}"
