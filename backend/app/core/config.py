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

    # --- Auth ---
    # Required in production. In development/test an ephemeral random secret is generated at
    # startup (tokens then do not survive restarts).
    jwt_secret: SecretStr | None = None
    access_token_ttl_minutes: int = Field(default=60, ge=5, le=24 * 60)

    # --- Rate limits (requests per window, per client IP or user) ---
    rate_limit_enabled: bool = True
    rate_limit_auth_per_minute: int = Field(default=10, ge=1)
    rate_limit_compute_per_minute: int = Field(default=60, ge=1)
    rate_limit_ingest_per_hour: int = Field(default=20, ge=1)
    rate_limit_market_data_per_minute: int = Field(default=120, ge=1)
    rate_limit_ai_per_hour: int = Field(default=30, ge=1)
    rate_limit_upload_per_hour: int = Field(default=20, ge=1)

    # --- Market data (India-first) ---
    # Default market for company routes that do not pass ?market=.
    default_market: Literal["IN", "US"] = "IN"
    # Prices, instrument directory and corporate actions. "demo" is deterministic synthetic data
    # (no network); "tej" is the free, keyless Tej API (NSE/BSE end-of-day bhavcopy data).
    market_data_provider: Literal["demo", "tej"] = "demo"
    # Financial statements for Indian companies. "demo" is synthetic; "yfinance" is the
    # unofficial Yahoo Finance library (optional extra, Yahoo terms: personal use only);
    # "none" disables statement ingestion for the Indian market.
    fundamentals_provider: Literal["demo", "yfinance", "none"] = "demo"
    market_data_timeout_seconds: float = Field(default=15.0, gt=0, le=120)
    # End-of-day data changes once per trading day, so responses are cached in-process.
    market_data_cache_ttl_seconds: int = Field(default=900, ge=0, le=24 * 3600)
    # A latest bar older than this many calendar days is flagged ``stale``.
    market_data_stale_after_days: int = Field(default=4, ge=1, le=30)

    # --- SEC EDGAR provider (optional, US market only) ---
    # SEC requires a descriptive User-Agent with contact info, e.g. "FinSight admin@example.com".
    # Ingestion is refused until this is set.
    sec_user_agent: str | None = None
    sec_timeout_seconds: float = Field(default=15.0, gt=0, le=120)

    # --- AI research assistant (Claude) ---
    # Backend-only; never exposed to the frontend. Without it, AI endpoints answer 503 and
    # everything else works.
    anthropic_api_key: SecretStr | None = None
    ai_model: str = "claude-opus-5-5"
    ai_timeout_seconds: float = Field(default=120.0, gt=0, le=600)
    ai_max_sources: int = Field(default=8, ge=1, le=20)

    # --- Annual report uploads ---
    upload_max_mb: int = Field(default=20, ge=1, le=25)  # nginx caps bodies at 25 MB
    upload_max_pages: int = Field(default=600, ge=1, le=2000)

    @field_validator("jwt_secret", "anthropic_api_key", "sec_user_agent", mode="before")
    @classmethod
    def _blank_is_unset(cls, value: object) -> object:
        # `FOO=` in .env or `${FOO:-}` in Compose yields "", which means "not configured".
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip().startswith("["):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
