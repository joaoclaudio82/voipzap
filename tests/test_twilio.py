import httpx
import pytest

from app.config import Settings
from app.providers.twilio import TwilioError, TwilioProvider


def make_settings(**over):
    base = dict(
        dry_run=False,
        twilio_account_sid="AC123",
        twilio_auth_token="tok-secreto",
        twilio_caller="+551150286739",
        twilio_voice="Polly.Camila",
    )
    base.update(over)
    return Settings(_env_file=None, **base)


def test_dry_run_does_not_call_network():
    provider = TwilioProvider(make_settings(dry_run=True))  # sem http: rede explodiria
    result = provider.send_voice_torpedo("5511987654321", "Olá, seu pedido chegou")
    assert result["dry_run"] is True
    assert result["called"] == "5511987654321"


def test_places_call_with_twiml_and_basic_auth():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import base64
        import urllib.parse

        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["form"] = dict(urllib.parse.parse_qsl(request.content.decode()))
        expected = base64.b64encode(b"AC123:tok-secreto").decode()
        assert captured["auth"] == f"Basic {expected}"
        return httpx.Response(201, json={"sid": "CA999", "status": "queued"})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    provider = TwilioProvider(make_settings(), http=http)
    result = provider.send_voice_torpedo("5511987654321", "Sua entrega chega hoje")

    assert result == {"sid": "CA999", "status": "queued"}
    assert captured["url"] == "https://api.twilio.com/2010-04-01/Accounts/AC123/Calls.json"
    assert captured["form"]["To"] == "+5511987654321"
    assert captured["form"]["From"] == "+551150286739"
    twiml = captured["form"]["Twiml"]
    assert 'voice="Polly.Camila"' in twiml
    assert 'language="pt-BR"' in twiml
    assert "Sua entrega chega hoje" in twiml


def test_escapes_xml_special_characters_in_message():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import urllib.parse

        captured["form"] = dict(urllib.parse.parse_qsl(request.content.decode()))
        return httpx.Response(201, json={"sid": "CA1", "status": "queued"})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    provider = TwilioProvider(make_settings(), http=http)
    provider.send_voice_torpedo("5511987654321", 'Pedido <A & B> "urgente"')

    twiml = captured["form"]["Twiml"]
    assert "&lt;A &amp; B&gt;" in twiml
    assert "<A & B>" not in twiml


def test_adds_plus_only_when_missing():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        import urllib.parse

        seen.append(dict(urllib.parse.parse_qsl(request.content.decode()))["To"])
        return httpx.Response(201, json={"sid": "CA1", "status": "queued"})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    provider = TwilioProvider(make_settings(), http=http)
    provider.send_voice_torpedo("5511987654321", "oi")
    provider.send_voice_torpedo("+5511987654321", "oi")
    assert seen == ["+5511987654321", "+5511987654321"]


def test_raises_on_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"message": "The 'To' number is not valid", "code": 21211})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    provider = TwilioProvider(make_settings(), http=http)
    with pytest.raises(TwilioError) as exc:
        provider.send_voice_torpedo("5511987654321", "oi")
    assert "21211" in str(exc.value) or "not valid" in str(exc.value)


def test_raises_without_credentials():
    provider = TwilioProvider(make_settings(twilio_account_sid="", twilio_auth_token=""))
    with pytest.raises(TwilioError) as exc:
        provider.send_voice_torpedo("5511987654321", "oi")
    assert "credenciais" in str(exc.value).lower()


def test_call_status_consulta_a_chamada():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/Calls/CA123.json")
        return httpx.Response(200, json={"status": "completed", "duration": "12"})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    provider = TwilioProvider(make_settings(), http=http)
    assert provider.call_status("CA123") == {
        "status": "completed", "duration": 12, "answered": True}


def test_call_status_marca_nao_atendida():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "no-answer", "duration": "0"})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    provider = TwilioProvider(make_settings(), http=http)
    resultado = provider.call_status("CA123")
    assert resultado["answered"] is False and resultado["status"] == "no-answer"


def test_call_status_em_dry_run_nao_chama_a_rede():
    provider = TwilioProvider(make_settings(dry_run=True))
    assert provider.call_status("CA123") == {"status": "dry_run", "duration": None, "answered": None}
