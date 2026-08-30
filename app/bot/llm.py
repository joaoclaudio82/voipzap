import logging

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)


class LLMError(Exception):
    pass


class OpenRouterClient:
    """Chat da OpenRouter (API compatível com OpenAI)."""

    def __init__(self, settings: Settings, http: httpx.Client | None = None):
        self.settings = settings
        self.http = http or httpx.Client(timeout=60)

    def complete(self, system: str, messages: list[dict]) -> str:
        payload = {
            "model": self.settings.openrouter_model,
            "messages": [{"role": "system", "content": system}, *messages],
            "max_tokens": 1024,
        }
        try:
            response = self.http.post(
                f"{self.settings.openrouter_base_url}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self.settings.openrouter_api_key}"},
            )
        except httpx.HTTPError as exc:
            raise LLMError(f"falha de rede ao chamar a OpenRouter: {exc}") from exc
        if response.status_code >= 400:
            raise LLMError(f"OpenRouter respondeu {response.status_code}: {response.text}")

        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise LLMError(f"OpenRouter não retornou choices: {data}")
        return (choices[0].get("message") or {}).get("content") or ""
