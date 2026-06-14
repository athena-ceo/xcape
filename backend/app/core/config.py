# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    environment: str = "development"
    secret_key: str = "dev-secret-change-me"
    default_locale: str = "fr"
    auto_verify_registrations: bool = True
    access_token_expire_minutes: int = 60 * 24 * 7
    # Comma-separated allowed CORS origins in production (path-based serving is
    # same-origin so this mainly matters if the frontend ever moves to a subdomain).
    cors_origins: str = "https://apps.athenadecisions.com"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    # Database
    postgres_server: str = "db"
    postgres_port: int = 5432
    postgres_db: str = "xcape_dev"
    postgres_user: str = "postgres"
    postgres_password: str = "password"

    # AI
    openai_api_key: str = ""
    openai_model: str = "gpt-5"  # research / scoring — accuracy matters
    # Chat assistant: a faster, cheaper model. It mostly calls tools and summarizes the
    # data we already hold, so the smaller model keeps replies snappy.
    openai_chat_model: str = "gpt-5-mini"
    openai_transcribe_model: str = "gpt-4o-mini-transcribe"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_server}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
