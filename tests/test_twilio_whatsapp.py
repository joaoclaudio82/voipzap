import httpx
import pytest

from app.config import Settings
from app.providers.twilio_whatsapp import TwilioWhatsAppError, TwilioWhatsAppProvider


def make_settings(**over):
    base = dict(
        dry_run=False,
        twilio_account_sid="AC123",
        twilio_auth_token="tok-secreto",
        twilio_whatsapp_from="+14155238886",
    )
    base.update(over)
    return Settings(_env_file=None, **base)


def test_dry_run_does_not_call_network():
    provider = TwilioWhatsAppProvider(make_settings(dry_run=True))
    result = provider.send_text("5511987654321", "olá!")
    assert result == {"dry_run": True, "number": "5511987654321", "text": "olá!"}


def test_sends_message_with_whatsapp_prefix():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import base64
        import urllib.parse

        captured["url"] = str(request.url)
        captured["form"] = dict(urllib.parse.parse_qsl(request.content.decode()))
        expected = base64.b64encode(b"AC123:tok-secreto").decode()
        assert request.headers.get("authorization") == f"Basic {expected}"
        return httpx.Response(201, json={"sid": "SM1", "status": "queued"})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    provider = TwilioWhatsAppProvider(make_settings(), http=http)
    result = provider.send_text("5511987654321", "sua entrega chegou")

    assert result == {"sid": "SM1", "status": "queued"}
    assert captured["url"] == "https://api.twilio.com/2010-04-01/Accounts/AC123/Messages.json"
    assert captured["form"] == {
        "To": "whatsapp:+5511987654321",
        "From": "whatsapp:+14155238886",
        "Body": "sua entrega chegou",
    }


def test_keeps_existing_whatsapp_prefix():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import urllib.parse

        captured["form"] = dict(urllib.parse.parse_qsl(request.content.decode()))
        return httpx.Response(201, json={"sid": "SM1"})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    provider = TwilioWhatsAppProvider(make_settings(), http=http)
    provider.send_text("whatsapp:+5511987654321", "oi")
    assert captured["form"]["To"] == "whatsapp:+5511987654321"


def test_raises_on_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"message": "not a valid WhatsApp sender", "code": 63007})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    provider = TwilioWhatsAppProvider(make_settings(), http=http)
    with pytest.raises(TwilioWhatsAppError) as exc:
        provider.send_text("5511987654321", "oi")
    assert "63007" in str(exc.value)


def test_raises_without_credentials():
    provider = TwilioWhatsAppProvider(make_settings(twilio_account_sid="", twilio_auth_token=""))
    with pytest.raises(TwilioWhatsAppError) as exc:
        provider.send_text("5511987654321", "oi")
    assert "credenciais" in str(exc.value).lower()
