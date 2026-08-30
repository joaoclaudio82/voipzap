import httpx
import pytest

from app.config import Settings
from app.providers.evolution import EvolutionError, EvolutionProvider


def make_settings(**over):
    base = dict(dry_run=False, evolution_url="http://localhost:8080",
                evolution_apikey="evo-key", evolution_instance="ligacao")
    base.update(over)
    return Settings(_env_file=None, **base)


def test_dry_run_does_not_call_network():
    provider = EvolutionProvider(make_settings(dry_run=True))
    result = provider.send_text("5532988887777", "olá!")
    assert result == {"dry_run": True, "number": "5532988887777", "text": "olá!"}


def test_sends_text_with_apikey():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json
        captured["url"] = str(request.url)
        captured["apikey"] = request.headers.get("apikey")
        captured["body"] = json.loads(request.content)
        return httpx.Response(201, json={"key": {"id": "3EB0"}})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    provider = EvolutionProvider(make_settings(), http=http)
    result = provider.send_text("5532988887777", "sua entrega chegou")

    assert result == {"key": {"id": "3EB0"}}
    assert captured["url"] == "http://localhost:8080/message/sendText/ligacao"
    assert captured["apikey"] == "evo-key"
    assert captured["body"] == {"number": "5532988887777", "text": "sua entrega chegou"}


def test_raises_on_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="instance not found")

    http = httpx.Client(transport=httpx.MockTransport(handler))
    provider = EvolutionProvider(make_settings(), http=http)
    with pytest.raises(EvolutionError) as exc:
        provider.send_text("5532988887777", "oi")
    assert "404" in str(exc.value)
