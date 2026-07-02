import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    openai_api_key: str
    jwt_secret: str
    jwt_access_ttl_minutes: int = 60
    jwt_refresh_ttl_days: int = 30
    ingest_api_key: str
    environment: str = "development"
    log_level: str = "INFO"

    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_base_url: str = "https://cloud.langfuse.com"  # EU region; use https://us.cloud.langfuse.com for US

    class Config:
        env_file = ".env"

    @property
    def langfuse_enabled(self) -> bool:
        return bool(self.langfuse_public_key and self.langfuse_secret_key)


settings = Settings()

# Langfuse SDK reads LANGFUSE_TRACING_ENABLED from the environment at first use;
# set it here (before any `from langfuse import ...`) so tracing is a no-op
# when no API keys are configured, instead of logging auth errors on every flush.
if not settings.langfuse_enabled:
    os.environ.setdefault("LANGFUSE_TRACING_ENABLED", "false")
