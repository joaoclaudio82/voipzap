import logging
import os

from fastapi import FastAPI

from app.bot.engine import BotEngine
from app.bot.llm import OpenRouterClient
from app.config import Settings
from app.db import Database
from app.providers.evolution import EvolutionProvider
from app.providers.nvoip import NvoipProvider
from app.providers.twilio import TwilioProvider
from app.providers.twilio_whatsapp import TwilioWhatsAppProvider
from app.routes import dev, notifications, twilio_webhook, webhook

logging.basicConfig(level=logging.INFO)


def _make_llm_client(settings: Settings):
    api_key = settings.openrouter_api_key or os.environ.get("OPENROUTER_API_KEY") or ""
    if not api_key:
        return None
    return OpenRouterClient(settings)


def _make_voice_provider(settings: Settings):
    """Provedor de voz escolhido por VOICE_PROVIDER (twilio | nvoip)."""
    if settings.voice_provider == "nvoip":
        return NvoipProvider(settings)
    return TwilioProvider(settings)


def _make_whatsapp_provider(settings: Settings):
    """Transporte de WhatsApp: twilio (oficial) ou evolution (não oficial)."""
    if settings.whatsapp_provider == "twilio":
        return TwilioWhatsAppProvider(settings)
    return EvolutionProvider(settings)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    db = Database(settings.db_path)

    app = FastAPI(title="ligacao")
    app.state.settings = settings
    app.state.db = db
    app.state.nvoip = _make_voice_provider(settings)
    app.state.evolution = _make_whatsapp_provider(settings)
    app.state.engine = BotEngine(settings, db, client=_make_llm_client(settings))

    app.include_router(notifications.router)
    app.include_router(webhook.router)
    app.include_router(twilio_webhook.router)
    if settings.dev_mode:
        app.include_router(dev.router)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    return app
