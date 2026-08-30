import hashlib
import hmac
import json

import httpx

from app.callbacks import notify_system
from app.config import Settings


def make_settings(**over):
    base = dict(callback_url="https://meusistema.exemplo/webhook", callback_secret="segredo")
    base.update(over)
    return Settings(_env_file=None, **base)


def test_envia_evento_assinado():
    capturado = {}

    def handler(request: httpx.Request) -> httpx.Response:
        capturado["url"] = str(request.url)
        capturado["assinatura"] = request.headers.get("x-signature")
        capturado["corpo"] = request.content
        return httpx.Response(200)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    notify_system(make_settings(), {"phone": "5511987654321", "message": "oi", "reply": "olá!"}, http=http)

    assert capturado["url"] == "https://meusistema.exemplo/webhook"
    corpo = json.loads(capturado["corpo"])
    assert corpo["phone"] == "5511987654321" and corpo["reply"] == "olá!"
    esperado = hmac.new(b"segredo", capturado["corpo"], hashlib.sha256).hexdigest()
    assert capturado["assinatura"] == esperado


def test_sem_url_configurada_nao_faz_nada():
    # sem http: se tentasse chamar a rede, o teste quebraria
    notify_system(make_settings(callback_url=""), {"phone": "1", "message": "a", "reply": "b"})


def test_falha_do_sistema_externo_nao_propaga():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sistema fora do ar")

    http = httpx.Client(transport=httpx.MockTransport(handler))
    notify_system(make_settings(), {"phone": "1", "message": "a", "reply": "b"}, http=http)


def test_resposta_de_erro_nao_propaga():
    http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500, text="erro")))
    notify_system(make_settings(), {"phone": "1", "message": "a", "reply": "b"}, http=http)
