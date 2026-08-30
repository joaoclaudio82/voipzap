from app.routes.webhook import Inbound, parse_evolution_event

FLAT = {
    "event": "messages.upsert",
    "instance": "ligacao",
    "data": {
        "key": {"remoteJid": "5532988887777@s.whatsapp.net", "fromMe": False, "id": "A1"},
        "message": {"conversation": "oi, quando chega?"},
    },
}

NESTED = {
    "event": "messages.upsert",
    "instance": "ligacao",
    "data": {
        "message": {
            "key": {"remoteJid": "5532988887777@s.whatsapp.net", "fromMe": False, "id": "A2"},
            "message": {"conversation": "formato aninhado"},
        }
    },
}


def test_parses_flat_format():
    assert parse_evolution_event(FLAT) == Inbound("5532988887777", "oi, quando chega?")


def test_parses_nested_format():
    assert parse_evolution_event(NESTED) == Inbound("5532988887777", "formato aninhado")


def test_parses_extended_text():
    payload = {
        "event": "messages.upsert",
        "data": {
            "key": {"remoteJid": "5532988887777@s.whatsapp.net", "fromMe": False},
            "message": {"extendedTextMessage": {"text": "com link"}},
        },
    }
    assert parse_evolution_event(payload) == Inbound("5532988887777", "com link")


def test_ignores_other_events_fromme_and_groups():
    assert parse_evolution_event({"event": "connection.update", "data": {}}) is None

    mine = {"event": "messages.upsert", "data": {
        "key": {"remoteJid": "5532988887777@s.whatsapp.net", "fromMe": True},
        "message": {"conversation": "eu mesmo"}}}
    assert parse_evolution_event(mine) is None

    group = {"event": "messages.upsert", "data": {
        "key": {"remoteJid": "12036304@g.us", "fromMe": False},
        "message": {"conversation": "grupo"}}}
    assert parse_evolution_event(group) is None


def test_media_message_has_none_text():
    payload = {"event": "messages.upsert", "data": {
        "key": {"remoteJid": "5532988887777@s.whatsapp.net", "fromMe": False},
        "message": {"audioMessage": {"seconds": 3}}}}
    parsed = parse_evolution_event(payload)
    assert parsed == Inbound("5532988887777", None)


def test_webhook_rejects_bad_token(client):
    response = client.post("/webhooks/whatsapp?token=errado", json=FLAT)
    assert response.status_code == 401


def test_webhook_replies_via_evolution(client):
    sent = []

    class SpyEvolution:
        def send_text(self, number, text):
            sent.append((number, text))
            return {"dry_run": True}

    client.app.state.evolution = SpyEvolution()
    response = client.post("/webhooks/whatsapp?token=test-webhook", json=FLAT)
    assert response.status_code == 200
    assert response.json() == {"status": "replied"}
    assert sent == [("5532988887777", "[sem IA] Recebi: oi, quando chega?")]


def test_webhook_ignores_unknown_payload(client):
    response = client.post("/webhooks/whatsapp?token=test-webhook",
                           json={"event": "qrcode.updated", "data": {}})
    assert response.status_code == 200
    assert response.json() == {"status": "ignored"}


def test_webhook_media_gets_fixed_reply(client):
    from app.routes.webhook import NON_TEXT_REPLY
    sent = []

    class SpyEvolution:
        def send_text(self, number, text):
            sent.append((number, text))
            return {"dry_run": True}

    client.app.state.evolution = SpyEvolution()
    payload = {"event": "messages.upsert", "data": {
        "key": {"remoteJid": "5532988887777@s.whatsapp.net", "fromMe": False},
        "message": {"imageMessage": {"caption": ""}}}}
    response = client.post("/webhooks/whatsapp?token=test-webhook", json=payload)
    assert response.status_code == 200
    assert sent == [("5532988887777", NON_TEXT_REPLY)]


def test_webhook_never_500s(client):
    class ExplodingEvolution:
        def send_text(self, number, text):
            raise RuntimeError("evolution fora do ar")

    client.app.state.evolution = ExplodingEvolution()
    response = client.post("/webhooks/whatsapp?token=test-webhook", json=FLAT)
    assert response.status_code == 200
    assert response.json() == {"status": "error-logged"}


def test_webhook_non_object_body_returns_200(client):
    response = client.post("/webhooks/whatsapp?token=test-webhook", json=[1, 2, 3])
    assert response.status_code == 200
    assert response.json() == {"status": "ignored"}


def test_webhook_invalid_json_returns_200(client):
    response = client.post("/webhooks/whatsapp?token=test-webhook",
                           content=b"not json",
                           headers={"Content-Type": "application/json"})
    assert response.status_code == 200
    assert response.json() == {"status": "error-logged"}


def test_webhook_bad_token_beats_bad_body(client):
    response = client.post("/webhooks/whatsapp?token=errado", content=b"not json",
                           headers={"Content-Type": "application/json"})
    assert response.status_code == 401


def test_webhook_logs_unrecognized_upsert(client, caplog):
    import logging

    payload = {"event": "messages.upsert", "data": {"weird": True}}
    with caplog.at_level(logging.WARNING, logger="app.routes.webhook"):
        response = client.post("/webhooks/whatsapp?token=test-webhook", json=payload)
    assert response.status_code == 200
    assert response.json() == {"status": "ignored"}
    assert any("payload não reconhecido" in record.getMessage() for record in caplog.records)
