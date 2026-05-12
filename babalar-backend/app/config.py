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

    class Config:
        env_file = ".env"


settings = Settings()
