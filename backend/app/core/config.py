"""Application settings, loaded from environment variables (and an optional .env file).

Secrets (database password, Anthropic API key, JWT secret) are only ever read here on the
backend. They are typed as ``SecretStr`` so they are masked in logs and reprs.
"""

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FINSIGHT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "FinSight API"
    environment: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_json: bool = True

    database_url: SecretStr = SecretStr(
        "postgresql+psycopg://finsight:finsight@localhost:5432/finsight"
    )
    db_pool_size: int = Field(default=5, ge=1, le=50)
    db_echo: bool = False

    # Comma-separated in the environment, e.g. "http://a.test,http://b.test".
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]

    # Reserved for later phases; never exposed to the frontend.
    anthropic_api_key: SecretStr | None = None
    jwt_secret: SecretStr | None = None

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip().startswith("["):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
