from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/events_aggregator"
    events_provider_base_url: str = "http://events-provider.dev-2.python-labs.ru"
    events_provider_api_key: str = ""
    sync_interval_seconds: int = 24 * 60 * 60
    seats_cache_seconds: int = 30

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
