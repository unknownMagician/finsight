import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.ratelimit import RateLimiter, retry_after_header
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    reset_security_caches,
    validate_security_settings,
    verify_password,
)


def test_password_hash_roundtrip() -> None:
    hashed = hash_password("a-long-password-123")
    assert hashed.startswith("$argon2id$")
    assert verify_password(hashed, "a-long-password-123")
    assert not verify_password(hashed, "wrong")
    assert not verify_password(None, "anything")
    assert not verify_password("not-a-hash", "anything")


def test_token_roundtrip_and_rejections(test_env: None) -> None:
    user_id = uuid.uuid4()
    token, expires_in = create_access_token(user_id)
    assert expires_in == 3600
    assert decode_access_token(token) == user_id
    assert decode_access_token(token + "x") is None
    expired, _ = create_access_token(user_id, now=datetime.now(UTC) - timedelta(hours=2))
    assert decode_access_token(expired) is None
    forged = jwt.encode(
        {"sub": str(user_id), "type": "access", "iat": 0, "exp": 9_999_999_999},
        "some-other-secret-that-is-long-enough-123",
        algorithm="HS256",
    )
    assert decode_access_token(forged) is None


def test_token_with_wrong_type_or_alg_none_rejected(test_env: None) -> None:
    token, _ = create_access_token(uuid.uuid4())
    payload = jwt.decode(token, options={"verify_signature": False})
    unsigned = jwt.encode({**payload, "type": "access"}, key="", algorithm="none")
    assert decode_access_token(unsigned) is None


def test_production_requires_strong_secret(test_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import get_settings

    monkeypatch.setenv("FINSIGHT_ENVIRONMENT", "production")
    monkeypatch.delenv("FINSIGHT_JWT_SECRET")
    get_settings.cache_clear()
    reset_security_caches()
    with pytest.raises(RuntimeError, match="required in production"):
        validate_security_settings()
    monkeypatch.setenv("FINSIGHT_JWT_SECRET", "short")
    get_settings.cache_clear()
    reset_security_caches()
    with pytest.raises(RuntimeError, match="at least 32"):
        validate_security_settings()


def test_rate_limiter_sliding_window() -> None:
    now = [0.0]
    limiter = RateLimiter(clock=lambda: now[0])
    assert [limiter.hit("k", 2, 60) for _ in range(2)] == [None, None]
    assert limiter.hit("k", 2, 60) == 60.0
    assert limiter.hit("other", 2, 60) is None  # keys are independent
    now[0] = 59.5
    assert limiter.hit("k", 2, 60) == pytest.approx(0.5)
    now[0] = 60.0
    assert limiter.hit("k", 2, 60) is None
    assert retry_after_header(0.2) == "1"
    limiter.reset()
    assert limiter.hit("k", 1, 60) is None
