import base64
import logging
import time

import httpx

from app.config import Settings
from app.providers.base import VoiceProviderError

logger = logging.getLogger(__name__)


class NvoipError(VoiceProviderError):
    pass


class NvoipProvider:
    def __init__(self, settings: Settings, http: httpx.Client | None = None):
        self.settings = settings
        self.http = http or httpx.Client(timeout=30)
        self._token = ""
        self._token_expires_at = 0.0

    def _access_token(self) -> str:
        """Token OAuth (client credentials), reaproveitado até perto de expirar."""
        if self._token and time.monotonic() < self._token_expires_at:
            return self._token
        pair = f"{self.settings.nvoip_client_id}:{self.settings.nvoip_client_secret}"
        basic = base64.b64encode(pair.encode()).decode()
        try:
            response = self.http.post(
                self.settings.nvoip_token_url,
                data={"grant_type": "client_credentials"},
                headers={
                    "Authorization": f"Basic {basic}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
        except httpx.HTTPError as exc:
            raise NvoipError(f"falha de rede ao obter token da Nvoip: {exc}") from exc
        if response.status_code >= 400:
            raise NvoipError(
                f"Nvoip recusou o token OAuth ({response.status_code}): {response.text}"
            )
        data = response.json()
        token = data.get("access_token")
        if not token:
            raise NvoipError(f"resposta de token da Nvoip sem access_token: {data}")
        self._token = token
        self._token_expires_at = time.monotonic() + max(int(data.get("expires_in", 3600)) - 60, 60)
        return token

    def send_voice_torpedo(self, called: str, message: str) -> dict:
        if self.settings.dry_run:
            logger.info("[DRY_RUN] torpedo de voz para %s: %r", called, message)
            return {"dry_run": True, "called": called, "message": message}

        payload = {
            "caller": self.settings.nvoip_caller,
            "called": called,
            "audios": [{"audio": message, "positionAudio": 1}],
            "dtmfs": [],
        }
        # A napikey (painel → API) autentica a API v2 por query param, sem
        # expiração; o Bearer estático fica como alternativa na v3.
        if self.settings.nvoip_client_id and self.settings.nvoip_client_secret:
            url = f"{self.settings.nvoip_base_url}/v3/torpedo/voice"
            params = None
            headers = {"Authorization": f"Bearer {self._access_token()}"}
        elif self.settings.nvoip_napikey:
            url = f"{self.settings.nvoip_base_url}/v2/torpedo/voice"
            params = {"napikey": self.settings.nvoip_napikey}
            headers = {}
        elif self.settings.nvoip_access_token:
            url = f"{self.settings.nvoip_base_url}/v3/torpedo/voice"
            params = None
            headers = {"Authorization": f"Bearer {self.settings.nvoip_access_token}"}
        else:
            raise NvoipError(
                "credenciais Nvoip ausentes: preencha NVOIP_CLIENT_ID/SECRET, "
                "NVOIP_NAPIKEY ou NVOIP_ACCESS_TOKEN no .env"
            )
        try:
            response = self.http.post(url, json=payload, params=params, headers=headers)
        except httpx.HTTPError as exc:
            raise NvoipError(f"falha de rede ao chamar a Nvoip: {exc}") from exc
        if response.status_code >= 400:
            raise NvoipError(f"Nvoip respondeu {response.status_code}: {response.text}")

        data = response.json()
        # A Nvoip aceita a requisição com HTTP 200 e sinaliza a falha da chamada
        # no corpo — sem isto um disparo que nunca tocou seria reportado como enviado.
        if str(data.get("status", "")).lower() in {"error", "failed"}:
            raise NvoipError(f"Nvoip não completou a ligação: {data}")
        return data
