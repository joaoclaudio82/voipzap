import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def settings_test(tmp_path, monkeypatch):
    # Garante que create_app não crie um client de LLM real nos testes.
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    return Settings(
        _env_file=None,
        api_key="test-key",
        openrouter_api_key="",
        twilio_auth_token="test-twilio-token",
        webhook_token="test-webhook",
        db_path=str(tmp_path / "test.db"),
        dry_run=True,
        dev_mode=True,
    )


@pytest.fixture
def client(settings_test):
    return TestClient(create_app(settings_test))
