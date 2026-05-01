"""
Application settings — loaded from .env via Pydantic BaseSettings.
All filter parameters that were previously hard-coded now live here
or in config/filter_profiles/*.json.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    app_env: str = "development"
    log_level: str = "INFO"

    # Database
    database_url: str = Field(..., description="Async SQLAlchemy URL (asyncpg)")
    sync_database_url: str = Field(..., description="Sync URL for Alembic")

    # Redis / Celery
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # Google
    google_service_account_json: str = "./secrets/google-service-account.json"
    google_sheets_id: str = ""
    google_sheets_worksheet: str = "Qualified Properties"
    google_calendar_id: str = "primary"
    google_oauth_client_secret: str = "./secrets/oauth-client-secret.json"
    google_oauth_token: str = "./secrets/oauth-token.json"

    # Email
    email_mode: str = "sendgrid"
    sendgrid_api_key: str = ""
    gmail_host: str = "smtp.gmail.com"
    gmail_port: int = 587
    gmail_username: str = ""
    gmail_app_password: str = ""
    sender_email: str = ""
    reply_to_email: str = ""

    # Outreach
    allow_automated_outreach: bool = False
    booking_url: str = ""

    # Notifications
    discord_webhook_url: str = ""

    # Zestimate
    zestimate_staleness_days: int = 7

    # Proxies
    use_proxies: bool = False
    proxies_file: str = "./config/proxies.txt"

    # Auth
    jwt_secret_key: str = Field(..., description="HS256 signing secret — required, no default")
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60


settings = Settings()
