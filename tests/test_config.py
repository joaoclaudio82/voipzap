from app.config import Settings


def test_settings_defaults(monkeypatch):
    for var in ("API_KEY", "DRY_RUN", "DEV_MODE"):
        monkeypatch.delenv(var, raising=False)
    s = Settings(_env_file=None)
    assert s.dry_run is True
    assert s.dev_mode is True
    assert s.openrouter_model == "minimax/minimax-m3:free"
    assert s.openrouter_base_url == "https://openrouter.ai/api/v1"
    assert s.nvoip_base_url == "https://api.nvoip.com.br"
    assert s.evolution_instance == "ligacao"
    assert s.db_path == "data/ligacao.db"


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("API_KEY", "k123")
    monkeypatch.setenv("DRY_RUN", "false")
    s = Settings(_env_file=None)
    assert s.api_key == "k123"
    assert s.dry_run is False
