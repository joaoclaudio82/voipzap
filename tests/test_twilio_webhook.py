import base64
import hashlib
import hmac

WEBHOOK_URL = "http://testserver/webhooks/twilio-whatsapp"


def sign(url: str, params: dict, token: str) -> str:
    data = url + "".join(f"{k}{params[k]}" for k in sorted(params))
    digest = hmac.new(token.encode(), data.encode(), hashlib.sha1).digest()
    return base64.b64encode(digest).decode()


def post(client, params, token="test-twilio-token", url=WEBHOOK_URL):
    return client.post(
        "/webhooks/twilio-whatsapp",
        data=params,
        headers={"X-Twilio-Signature": sign(url, params, token)},
    )


def test_rejects_invalid_signature(client):
    response = client.post(
        "/webhooks/twilio-whatsapp",
        data={"From": "whatsapp:+5511987654321", "Body": "oi"},
        headers={"X-Twilio-Signature": "assinatura-errada"},
    )
    assert response.status_code == 403


def test_replies_to_incoming_message(client):
    sent = []

    class SpyWhatsApp:
        def send_text(self, number, text):
            sent.append((number, text))
            return {"sid": "SM1"}

    client.app.state.evolution = SpyWhatsApp()
    response = post(client, {"From": "whatsapp:+5511987654321", "Body": "cadê meu pedido?"})

    assert response.status_code == 200
    assert response.json() == {"status": "replied"}
    assert sent == [("5511987654321", "[sem IA] Recebi: cadê meu pedido?")]


def test_ignores_message_without_text(client):
    response = post(client, {"From": "whatsapp:+5511987654321", "Body": ""})
    assert response.status_code == 200
    assert response.json() == {"status": "ignored"}


def test_never_500s(client):
    class ExplodingWhatsApp:
        def send_text(self, number, text):
            raise RuntimeError("twilio fora do ar")

    client.app.state.evolution = ExplodingWhatsApp()
    response = post(client, {"From": "whatsapp:+5511987654321", "Body": "oi"})
    assert response.status_code == 200
    assert response.json() == {"status": "error-logged"}
