import httpx
import pytest

from app.bot.llm import LLMError, OpenRouterClient
from app.config import Settings


def make_settings(**over):
    base = dict(
        openrouter_api_key="sk-or-teste",
        openrouter_model="minimax/minimax-m3:free",
        openrouter_base_url="https://openrouter.ai/api/v1",
    )
    base.update(over)
    return Settings(_env_file=None, **base)


def test_sends_chat_completion_with_system_first():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "Sua entrega chega às 15h."}}]}
        )

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = OpenRouterClient(make_settings(), http=http)
    reply = client.complete("persona do bot", [{"role": "user", "content": "cadê meu pedido?"}])

    assert reply == "Sua entrega chega às 15h."
    assert captured["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert captured["auth"] == "Bearer sk-or-teste"
    assert captured["body"]["model"] == "minimax/minimax-m3:free"
    assert captured["body"]["messages"] == [
        {"role": "system", "content": "persona do bot"},
        {"role": "user", "content": "cadê meu pedido?"},
    ]


def test_raises_on_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(402, text="insufficient credits")

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = OpenRouterClient(make_settings(), http=http)
    with pytest.raises(LLMError) as exc:
        client.complete("s", [{"role": "user", "content": "oi"}])
    assert "402" in str(exc.value)


def test_raises_when_response_has_no_choices():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"error": {"message": "rate limited"}})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = OpenRouterClient(make_settings(), http=http)
    with pytest.raises(LLMError):
        client.complete("s", [{"role": "user", "content": "oi"}])


def test_returns_empty_string_when_content_is_null():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": None}}]})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = OpenRouterClient(make_settings(), http=http)
    assert client.complete("s", [{"role": "user", "content": "oi"}]) == ""
