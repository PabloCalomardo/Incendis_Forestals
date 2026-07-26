from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    project_name: str = "wildfire-intelligence-platform"
    environment: str = "development"
    log_level: str = "INFO"
    api_version: str = "0.1.0"
    api_cors_origins: str = "http://localhost:3000"

    database_url: str = "postgresql+asyncpg://wildfire:change-me-local@postgres:5432/wildfire"
    redis_url: str = "redis://redis:6379/0"
    minio_endpoint: str = "http://minio:9000"
    minio_bucket_raw: str = "raw-ingestion"
    s3_access_key_id: str = Field(default="", repr=False)
    s3_secret_access_key: str = Field(default="", repr=False)
    s3_region: str = "eu-west-1"

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.api_cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
