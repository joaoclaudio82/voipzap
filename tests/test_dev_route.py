from fastapi.testclient import TestClient

from app.main import create_app


def test_dev_chat_returns_reply(client):
    response = client.post("/dev/chat", json={"phone": "5532988887777", "text": "olá"})
    assert response.status_code == 200
    assert response.json() == {"reply": "[sem IA] Recebi: olá"}


def test_dev_chat_absent_when_dev_mode_off(settings_test):
    settings_test.dev_mode = False
    app = create_app(settings_test)
    response = TestClient(app).post("/dev/chat",
                                    json={"phone": "5532988887777", "text": "olá"})
    assert response.status_code == 404
