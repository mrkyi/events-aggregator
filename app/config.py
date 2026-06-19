from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = ""
    events_provider_base_url: str = (
        "http://student-system-events-provider-web.student-system-events-provider.svc:8000"
    )
    events_provider_api_key: str = ""
    sync_interval_seconds: int = 24 * 60 * 60
    seats_cache_seconds: int = 30

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
