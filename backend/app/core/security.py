"""Password hashing (Argon2id) and JWT access tokens (HS256)."""

import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from functools import lru_cache

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import Settings, get_settings

logger = logging.getLogger("app.security")

_hasher = PasswordHasher()  # argon2id with library-recommended parameters
_ALGORITHM = "HS256"
_TOKEN_TYPE = "access"  # noqa: S105 - JWT "type" claim, not a secret

# Verified against when the user does not exist, so login timing does not reveal whether an
# email is registered.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


@lru_cache
def _jwt_secret() -> str:
    settings: Settings = get_settings()
    if settings.jwt_secret is not None:
        secret = settings.jwt_secret.get_secret_value()
        if len(secret) < 32:
            raise RuntimeError("FINSIGHT_JWT_SECRET must be at least 32 characters")
        return secret
    if settings.environment == "production":
        raise RuntimeError("FINSIGHT_JWT_SECRET is required in production")
    logger.warning("jwt_secret_not_configured_using_ephemeral_secret")
    return secrets.token_urlsafe(48)


def reset_security_caches() -> None:
    _jwt_secret.cache_clear()


def validate_security_settings() -> None:
    """Fail fast at startup on misconfigured secrets."""
    _jwt_secret()


def create_access_token(user_id: uuid.UUID, now: datetime | None = None) -> tuple[str, int]:
    """Return (token, expires_in_seconds)."""
    settings = get_settings()
    issued = now or datetime.now(UTC)
    ttl = timedelta(minutes=settings.access_token_ttl_minutes)
    payload = {
        "sub": str(user_id),
        "type": _TOKEN_TYPE,
        "iat": issued,
        "exp": issued + ttl,
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, _jwt_secret(), algorithm=_ALGORITHM), int(ttl.total_seconds())


def decode_access_token(token: str) -> uuid.UUID | None:
    """Return the user ID for a valid, unexpired access token; otherwise None."""
    try:
        payload = jwt.decode(
            token,
            _jwt_secret(),
            algorithms=[_ALGORITHM],
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.PyJWTError:
        return None
    if payload.get("type") != _TOKEN_TYPE:
        return None
    try:
        return uuid.UUID(str(payload["sub"]))
    except ValueError:
        return None
