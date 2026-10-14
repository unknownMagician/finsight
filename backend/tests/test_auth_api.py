from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from tests.conftest import TEST_PASSWORD

AUTH = "/api/v1/auth"


def test_register_login_me(client: TestClient) -> None:
    r = client.post(
        f"{AUTH}/register",
        json={"email": "Bob@Example.com", "password": TEST_PASSWORD, "display_name": "Bob"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == "bob@example.com"
    assert "password" not in r.text and "hash" not in r.text

    r = client.post(f"{AUTH}/login", json={"email": "BOB@example.com", "password": TEST_PASSWORD})
    assert r.status_code == 200
    token = r.json()
    assert token["token_type"] == "bearer" and token["expires_in"] == 3600

    me = client.get(f"{AUTH}/me", headers={"Authorization": f"Bearer {token['access_token']}"})
    assert me.status_code == 200
    assert me.json()["id"] == body["id"]


def test_duplicate_email_case_insensitive(client: TestClient) -> None:
    payload = {"email": "dup@example.com", "password": TEST_PASSWORD}
    assert client.post(f"{AUTH}/register", json=payload).status_code == 201
    r = client.post(f"{AUTH}/register", json={**payload, "email": "DUP@example.com"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "email_already_registered"


@pytest.mark.parametrize(
    "payload",
    [
        {"email": "not-an-email", "password": TEST_PASSWORD},
        {"email": "x@example.com", "password": "short"},
        {"email": "x@example.com", "password": "p" * 129},
        {"email": "x@example.com", "password": TEST_PASSWORD, "is_admin": True},
    ],
)
def test_register_validation(client: TestClient, payload: dict[str, object]) -> None:
    r = client.post(f"{AUTH}/register", json=payload)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


def test_login_failures_are_indistinguishable(
    client: TestClient, register_and_login: Callable[[str], dict[str, str]]
) -> None:
    register_and_login("carol@example.com")
    wrong_password = client.post(
        f"{AUTH}/login", json={"email": "carol@example.com", "password": "wrong-password-123"}
    )
    unknown_user = client.post(
        f"{AUTH}/login", json={"email": "nobody@example.com", "password": "wrong-password-123"}
    )
    assert wrong_password.status_code == unknown_user.status_code == 401
    assert wrong_password.json()["error"]["message"] == unknown_user.json()["error"]["message"]


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer not-a-jwt"}, {"Authorization": "Basic dXNlcjpwYXNz"}],
)
def test_protected_endpoint_rejects_missing_or_bad_tokens(
    client: TestClient, headers: dict[str, str]
) -> None:
    r = client.get(f"{AUTH}/me", headers=headers)
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "not_authenticated"
    assert r.headers["www-authenticate"] == "Bearer"


def test_token_for_deactivated_user_rejected(client: TestClient, auth: dict[str, str]) -> None:
    from sqlalchemy import update

    from app.db.session import get_sessionmaker
    from app.models import User

    with get_sessionmaker()() as db:
        db.execute(update(User).values(is_active=False))
        db.commit()
    assert client.get(f"{AUTH}/me", headers=auth).status_code == 401


def test_login_is_rate_limited(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import get_settings

    monkeypatch.setenv("FINSIGHT_RATE_LIMIT_AUTH_PER_MINUTE", "3")
    get_settings.cache_clear()
    payload = {"email": "rl@example.com", "password": "wrong-password-123"}
    statuses = [client.post(f"{AUTH}/login", json=payload).status_code for _ in range(4)]
    assert statuses == [401, 401, 401, 429]
    r = client.post(f"{AUTH}/login", json=payload)
    assert r.json()["error"]["code"] == "rate_limited"
    assert int(r.headers["retry-after"]) >= 1
