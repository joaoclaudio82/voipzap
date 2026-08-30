import logging

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)


class EvolutionError(Exception):
    pass


class EvolutionProvider:
    def __init__(self, settings: Settings, http: httpx.Client | None = None):
        self.settings = settings
        self.http = http or httpx.Client(timeout=30)

    def send_text(self, number: str, text: str) -> dict:
        if self.settings.dry_run:
            logger.info("[DRY_RUN] whatsapp para %s: %r", number, text)
            return {"dry_run": True, "number": number, "text": text}

        url = f"{self.settings.evolution_url}/message/sendText/{self.settings.evolution_instance}"
        try:
            response = self.http.post(
                url,
                json={"number": number, "text": text},
                headers={"apikey": self.settings.evolution_apikey},
            )
        except httpx.HTTPError as exc:
            raise EvolutionError(f"falha de rede ao chamar a Evolution: {exc}") from exc
        if response.status_code >= 400:
            raise EvolutionError(f"Evolution respondeu {response.status_code}: {response.text}")
        return response.json()
