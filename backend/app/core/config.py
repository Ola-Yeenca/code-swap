from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Claude Codex Wrapper API"
    app_env: str = "development"
    api_prefix: str = "/v1"
    frontend_origin: str = "http://localhost:5173"
    frontend_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    sentry_dsn: str = ""

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/wrapper"
    redis_url: str = "redis://localhost:6379/0"

    session_secret: str = Field(default="change-me", min_length=8)
    magic_link_signer_salt: str = "magic-link"
    encryption_key: str = ""

    billing_enabled: bool = False
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_id: str = ""
    billing_success_url: str = "http://localhost:5173/billing/success"
    billing_cancel_url: str = "http://localhost:5173/billing/cancel"
    billing_portal_return_url: str = "http://localhost:5173/settings/billing"

    openai_base_url: str = "https://api.openai.com/v1"
    anthropic_base_url: str = "https://api.anthropic.com/v1"

    r2_endpoint: str = ""
    r2_bucket: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""

    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = ""

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_use_tls: bool = True

    default_data_region: str = "us"
    auto_create_tables: bool = True
    model_catalog_refresh_minutes: int = 360

    @property
    def cors_origins(self) -> list[str]:
        origins: list[str] = []
        if self.frontend_origin:
            origins.append(self.frontend_origin.strip())
        if self.frontend_origins:
            origins.extend(
                [origin.strip() for origin in self.frontend_origins.split(",") if origin.strip()]
            )

        deduped: list[str] = []
        seen: set[str] = set()
        for origin in origins:
            if origin in seen:
                continue
            seen.add(origin)
            deduped.append(origin)
        return deduped


@lru_cache
def get_settings() -> Settings:
    return Settings()
