from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = Field(
        default="",
        validation_alias=AliasChoices("DATABASE_URL", "POSTGRES_CONNECTION_STRING"),
    )
    postgres_host: str = Field(
        default="",
        validation_alias=AliasChoices("POSTGRES_HOST", "DB_HOST"),
    )
    postgres_port: str = Field(
        default="5432",
        validation_alias=AliasChoices("POSTGRES_PORT", "DB_PORT"),
    )
    postgres_db: str = Field(
        default="",
        validation_alias=AliasChoices("POSTGRES_DB", "POSTGRES_DATABASE_NAME", "DB_NAME"),
    )
    postgres_user: str = Field(
        default="",
        validation_alias=AliasChoices("POSTGRES_USER", "POSTGRES_USERNAME", "DB_USER"),
    )
    postgres_password: str = Field(
        default="",
        validation_alias=AliasChoices("POSTGRES_PASSWORD", "DB_PASSWORD"),
    )
    events_provider_base_url: str = (
        "http://student-system-events-provider-web.student-system-events-provider.svc:8000"
    )
    events_provider_api_key: str = Field(
        default="",
        validation_alias=AliasChoices(
            "EVENTS_PROVIDER_API_KEY",
            "EVENTS_PROVIDER_KEY",
            "API_KEY",
            "LMS_API_KEY",
        ),
    )
    sync_interval_seconds: int = 24 * 60 * 60
    seats_cache_seconds: int = 30

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
