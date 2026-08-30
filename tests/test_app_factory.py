from app.main import create_app


def test_engine_gets_client_when_openrouter_key_present(settings_test):
    settings_test.openrouter_api_key = "sk-or-teste-123"
    application = create_app(settings_test)
    client = application.state.engine.client
    assert client is not None
    assert client.settings.openrouter_api_key == "sk-or-teste-123"


def test_engine_has_no_client_without_key(settings_test):
    application = create_app(settings_test)
    assert application.state.engine.client is None


def test_voice_provider_defaults_to_twilio(settings_test):
    from app.providers.twilio import TwilioProvider

    application = create_app(settings_test)
    assert isinstance(application.state.nvoip, TwilioProvider)


def test_voice_provider_can_be_nvoip(settings_test):
    from app.providers.nvoip import NvoipProvider

    settings_test.voice_provider = "nvoip"
    application = create_app(settings_test)
    assert isinstance(application.state.nvoip, NvoipProvider)
