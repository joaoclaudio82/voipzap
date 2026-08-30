def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_requires_api_key(client):
    response = client.post("/api/notifications", json={
        "phone": "5532988887777", "voice_message": "oi"})
    assert response.status_code == 401

    response = client.post("/api/notifications", json={
        "phone": "5532988887777", "voice_message": "oi"},
        headers={"X-API-Key": "errada"})
    assert response.status_code == 401


def test_rejects_invalid_phone(client):
    for phone in ["32988887777", "5532abc87777", "+5532988887777", "55329888877771234"]:
        response = client.post("/api/notifications",
                               json={"phone": phone, "voice_message": "oi"},
                               headers={"X-API-Key": "test-key"})
        assert response.status_code == 422, phone


def test_creates_notification_dry_run(client):
    response = client.post("/api/notifications", json={
        "phone": "5532988887777",
        "voice_message": "Seu pedido saiu para entrega",
        "context": "Pedido 123",
    }, headers={"X-API-Key": "test-key"})
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "dry_run"
    assert body["nvoip"]["dry_run"] is True
    assert isinstance(body["id"], int)


def test_returns_502_on_nvoip_error(client):
    from app.providers.nvoip import NvoipError

    class FailingNvoip:
        def send_voice_torpedo(self, called, message):
            raise NvoipError("Nvoip respondeu 500: boom")

    client.app.state.nvoip = FailingNvoip()
    response = client.post("/api/notifications", json={
        "phone": "5532988887777", "voice_message": "oi"},
        headers={"X-API-Key": "test-key"})
    assert response.status_code == 502
    assert "Nvoip" in response.json()["detail"]


def test_returns_502_on_twilio_error(client):
    from app.providers.twilio import TwilioError

    class FailingTwilio:
        def send_voice_torpedo(self, called, message):
            raise TwilioError("Twilio respondeu 400: número inválido")

    client.app.state.nvoip = FailingTwilio()
    response = client.post("/api/notifications", json={
        "phone": "5511987654321", "voice_message": "oi"},
        headers={"X-API-Key": "test-key"})
    assert response.status_code == 502
    assert "Twilio" in response.json()["detail"]
