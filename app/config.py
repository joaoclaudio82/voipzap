from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    api_key: str = "change-me"
    openrouter_api_key: str = ""
    openrouter_model: str = "minimax/minimax-m3:free"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    nvoip_access_token: str = ""
    nvoip_napikey: str = ""
    nvoip_client_id: str = ""
    nvoip_client_secret: str = ""
    nvoip_token_url: str = "https://api.nvoip.com.br/auth/oauth2/token"
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_caller: str = ""
    twilio_voice: str = "Polly.Camila"
    twilio_whatsapp_from: str = "+14155238886"
    voice_provider: str = "twilio"
    whatsapp_provider: str = "evolution"
    nvoip_caller: str = ""
    nvoip_base_url: str = "https://api.nvoip.com.br"
    evolution_url: str = "http://localhost:8080"
    evolution_apikey: str = ""
    evolution_instance: str = "ligacao"
    webhook_token: str = "change-me"
    business_name: str = "nossa empresa"
    db_path: str = "data/ligacao.db"
    dry_run: bool = True
    dev_mode: bool = True
