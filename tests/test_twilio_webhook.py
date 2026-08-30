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

    client.app.state.whatsapp_twilio = SpyWhatsApp()
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

    client.app.state.whatsapp_twilio = ExplodingWhatsApp()
    response = post(client, {"From": "whatsapp:+5511987654321", "Body": "oi"})
    assert response.status_code == 200
    assert response.json() == {"status": "error-logged"}


def test_avisa_o_sistema_do_cliente_quando_chega_mensagem(client, monkeypatch):
    enviados = []

    class SpyWhatsApp:
        def send_text(self, number, text):
            return {"sid": "SM1"}

    monkeypatch.setattr("app.routes.twilio_webhook.notify_system",
                        lambda settings, event, **kw: enviados.append(event))
    client.app.state.whatsapp_twilio = SpyWhatsApp()
    post(client, {"From": "whatsapp:+5511987654321", "Body": "cadê meu pedido?"})

    assert len(enviados) == 1
    evento = enviados[0]
    assert evento["phone"] == "5511987654321"
    assert evento["message"] == "cadê meu pedido?"
    assert evento["reply"] == "[sem IA] Recebi: cadê meu pedido?"
    assert "received_at" in evento


def test_falha_no_callback_nao_impede_resposta_ao_cliente(client, monkeypatch):
    enviados = []

    class SpyWhatsApp:
        def send_text(self, number, text):
            enviados.append(text)
            return {"sid": "SM1"}

    def explode(*a, **kw):
        raise RuntimeError("sistema do cliente fora do ar")

    monkeypatch.setattr("app.routes.twilio_webhook.notify_system", explode)
    client.app.state.whatsapp_twilio = SpyWhatsApp()
    resposta = post(client, {"From": "whatsapp:+5511987654321", "Body": "oi"})

    assert resposta.status_code == 200
    assert enviados, "o cliente precisa receber a resposta mesmo com o callback falhando"


def test_responde_pelo_twilio_mesmo_com_evolution_ativa(client):
    """A resposta volta pelo canal de entrada, não pelo provedor configurado."""
    twilio_enviou, evolution_enviou = [], []

    class Spy:
        def __init__(self, destino):
            self.destino = destino

        def send_text(self, number, text):
            self.destino.append((number, text))
            return {"sid": "SM1"}

    client.app.state.whatsapp_twilio = Spy(twilio_enviou)
    client.app.state.whatsapp_evolution = Spy(evolution_enviou)
    post(client, {"From": "whatsapp:+5511987654321", "Body": "oi"})

    assert len(twilio_enviou) == 1
    assert evolution_enviou == []
