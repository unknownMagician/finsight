"""Shared FastAPI dependencies: DB session, current user, rate limits, data provider."""

import uuid
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.ratelimit import RateLimiter, retry_after_header
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import User
from app.providers.base import FinancialDataProvider
from app.providers.sec_edgar import SecEdgarProvider

DbSession = Annotated[Session, Depends(get_db)]

_bearer = HTTPBearer(auto_error=False)


def _unauthorized(message: str = "Authentication required") -> AppError:
    return AppError("not_authenticated", message, 401, headers={"WWW-Authenticate": "Bearer"})


def get_current_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()
    user_id = decode_access_token(credentials.credentials)
    if user_id is None:
        raise _unauthorized("Invalid or expired token")
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise _unauthorized("Invalid or expired token")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


# --- rate limits ----------------------------------------------------------------------------


def get_rate_limiter(request: Request) -> RateLimiter:
    limiter: RateLimiter = request.app.state.rate_limiter
    return limiter


def _enforce(limiter: RateLimiter, key: str, limit: int, window: float) -> None:
    if not get_settings().rate_limit_enabled:
        return
    retry_in = limiter.hit(key, limit, window)
    if retry_in is not None:
        raise AppError(
            "rate_limited",
            "Too many requests; slow down",
            429,
            headers={"Retry-After": retry_after_header(retry_in)},
        )


def limit_by_ip(scope: str, setting: str, window_seconds: float) -> Callable[..., None]:
    def dependency(
        request: Request, limiter: Annotated[RateLimiter, Depends(get_rate_limiter)]
    ) -> None:
        client = request.client.host if request.client else "unknown"
        _enforce(limiter, f"{scope}:ip:{client}", getattr(get_settings(), setting), window_seconds)

    return dependency


def limit_by_user(scope: str, setting: str, window_seconds: float) -> Callable[..., None]:
    def dependency(
        user: CurrentUser, limiter: Annotated[RateLimiter, Depends(get_rate_limiter)]
    ) -> None:
        _enforce(
            limiter, f"{scope}:user:{user.id}", getattr(get_settings(), setting), window_seconds
        )

    return dependency


AuthRateLimit = Depends(limit_by_ip("auth", "rate_limit_auth_per_minute", 60))
ComputeRateLimit = Depends(limit_by_user("compute", "rate_limit_compute_per_minute", 60))
IngestRateLimit = Depends(limit_by_user("ingest", "rate_limit_ingest_per_hour", 3600))


# --- provider -------------------------------------------------------------------------------


def get_provider(request: Request) -> FinancialDataProvider:
    provider: FinancialDataProvider | None = getattr(request.app.state, "provider", None)
    if provider is not None:
        return provider
    settings = get_settings()
    if not settings.sec_user_agent:
        raise AppError(
            "provider_not_configured",
            "Financial data ingestion is not configured (FINSIGHT_SEC_USER_AGENT)",
            503,
        )
    edgar = SecEdgarProvider(settings.sec_user_agent, timeout=settings.sec_timeout_seconds)
    request.app.state.provider = edgar
    return edgar


Provider = Annotated[FinancialDataProvider, Depends(get_provider)]


def parse_uuid(raw: str, resource: str) -> uuid.UUID:
    try:
        return uuid.UUID(raw)
    except ValueError:
        raise AppError("not_found", f"{resource} not found", 404) from None
