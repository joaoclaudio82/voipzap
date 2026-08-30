import httpx
import pytest

from app.config import Settings
from app.providers.nvoip import NvoipError, NvoipProvider


def make_settings(**over):
    base = dict(dry_run=False, nvoip_access_token="tok-abc", nvoip_caller="553230000000")
    base.update(over)
    return Settings(_env_file=None, **base)


def test_sends_torpedo_v2_with_napikey():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"status": "ok"})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    provider = NvoipProvider(
        make_settings(nvoip_access_token="", nvoip_napikey="napi-123", nvoip_caller="149290001"),
        http=http,
    )
    result = provider.send_voice_torpedo("5532988887777", "Sua entrega chega hoje")

    assert result == {"status": "ok"}
    assert captured["url"] == "https://api.nvoip.com.br/v2/torpedo/voice?napikey=napi-123"
    assert captured["auth"] is None
    assert captured["body"] == {
        "caller": "149290001",
        "called": "5532988887777",
        "audios": [{"audio": "Sua entrega chega hoje", "positionAudio": 1}],
        "dtmfs": [],
    }


def test_napikey_takes_precedence_over_access_token():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"status": "ok"})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    provider = NvoipProvider(make_settings(nvoip_napikey="napi-123"), http=http)
    provider.send_voice_torpedo("5532988887777", "oi")
    assert "/v2/torpedo/voice" in captured["url"]


def test_raises_without_credentials():
    provider = NvoipProvider(make_settings(nvoip_access_token="", nvoip_napikey=""))
    with pytest.raises(NvoipError) as exc:
        provider.send_voice_torpedo("5532988887777", "oi")
    assert "credenciais" in str(exc.value).lower()


def test_dry_run_does_not_call_network():
    provider = NvoipProvider(make_settings(dry_run=True))  # sem http: rede explodiria
    result = provider.send_voice_torpedo("5532988887777", "Olá, seu pedido chegou")
    assert result["dry_run"] is True
    assert result["called"] == "5532988887777"


def test_sends_torpedo_with_bearer_and_payload():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        import json
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"status": "ok", "id": 42})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    provider = NvoipProvider(make_settings(), http=http)
    result = provider.send_voice_torpedo("5532988887777", "Sua entrega chega hoje")

    assert result == {"status": "ok", "id": 42}
    assert captured["url"] == "https://api.nvoip.com.br/v3/torpedo/voice"
    assert captured["auth"] == "Bearer tok-abc"
    assert captured["body"] == {
        "caller": "553230000000",
        "called": "5532988887777",
        "audios": [{"audio": "Sua entrega chega hoje", "positionAudio": 1}],
        "dtmfs": [],
    }


def test_raises_nvoip_error_on_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid token"})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    provider = NvoipProvider(make_settings(), http=http)
    with pytest.raises(NvoipError) as exc:
        provider.send_voice_torpedo("5532988887777", "oi")
    assert "401" in str(exc.value)


def test_raises_when_nvoip_payload_reports_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "error", "uuid": "abc", "called": "5511987654321"})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    provider = NvoipProvider(make_settings(nvoip_napikey="napi-123"), http=http)
    with pytest.raises(NvoipError) as exc:
        provider.send_voice_torpedo("5511987654321", "oi")
    assert "abc" in str(exc.value)


def test_accepts_successful_payload_status():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "queued", "uuid": "ok-1"})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    provider = NvoipProvider(make_settings(nvoip_napikey="napi-123"), http=http)
    assert provider.send_voice_torpedo("5511987654321", "oi")["uuid"] == "ok-1"


def _oauth_settings(**over):
    base = dict(
        dry_run=False,
        nvoip_access_token="",
        nvoip_napikey="",
        nvoip_client_id="nvoip_cid",
        nvoip_client_secret="segredo",
        nvoip_caller="149290001",
    )
    base.update(over)
    return Settings(_env_file=None, **base)


def test_oauth_fetches_token_then_calls_v3():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        import base64
        import json

        seen.append(str(request.url))
        if request.url.path.endswith("/auth/oauth2/token"):
            expected = base64.b64encode(b"nvoip_cid:segredo").decode()
            assert request.headers["authorization"] == f"Basic {expected}"
            assert b"grant_type=client_credentials" in request.content
            return httpx.Response(200, json={"access_token": "tok-oauth", "expires_in": 86399})
        assert request.headers["authorization"] == "Bearer tok-oauth"
        assert json.loads(request.content)["caller"] == "149290001"
        return httpx.Response(200, json={"status": "queued", "uuid": "u1"})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    provider = NvoipProvider(_oauth_settings(), http=http)
    assert provider.send_voice_torpedo("5511987654321", "oi")["uuid"] == "u1"
    assert seen[0].endswith("/auth/oauth2/token")
    assert seen[1] == "https://api.nvoip.com.br/v3/torpedo/voice"


def test_oauth_token_is_reused_between_calls():
    token_calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/auth/oauth2/token"):
            token_calls.append(1)
            return httpx.Response(200, json={"access_token": "tok-oauth", "expires_in": 86399})
        return httpx.Response(200, json={"status": "queued"})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    provider = NvoipProvider(_oauth_settings(), http=http)
    provider.send_voice_torpedo("5511987654321", "um")
    provider.send_voice_torpedo("5511987654321", "dois")
    assert len(token_calls) == 1


def test_oauth_token_failure_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="unauthorized")

    http = httpx.Client(transport=httpx.MockTransport(handler))
    provider = NvoipProvider(_oauth_settings(), http=http)
    with pytest.raises(NvoipError) as exc:
        provider.send_voice_torpedo("5511987654321", "oi")
    assert "token" in str(exc.value).lower()
