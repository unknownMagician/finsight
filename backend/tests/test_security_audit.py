"""Phase 7 audit guards: every route is authenticated (except an explicit allow-list), security
headers are present, and no secret or provider credential leaks into responses."""

import re

from fastapi.testclient import TestClient

PUBLIC = {
    ("GET", "/api/v1/health/live"),
    ("GET", "/api/v1/health/ready"),
    ("POST", "/api/v1/auth/register"),
    ("POST", "/api/v1/auth/login"),
}


def _concrete(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "00000000-0000-0000-0000-000000000000", path).replace(
        "/pages/00000000-0000-0000-0000-000000000000", "/pages/1"
    )


def test_every_non_public_route_requires_authentication(client: TestClient) -> None:
    # The OpenAPI document lists every mounted endpoint (included routers are nested lazily).
    paths = client.app.openapi()["paths"]  # type: ignore[attr-defined]
    checked = 0
    for raw_path, operations in paths.items():
        for method in operations:
            method = method.upper()
            if (method, raw_path) in PUBLIC:
                continue
            path = _concrete(raw_path).replace(
                "/companies/00000000-0000-0000-0000-000000000000", "/companies/DEMOINFO"
            )
            response = client.request(method, path)
            assert response.status_code == 401, f"{method} {raw_path} -> {response.status_code}"
            assert response.json()["error"]["code"] == "not_authenticated"
            checked += 1
    assert checked >= 40, checked  # the guard actually covered the API surface


def test_security_headers_on_api_responses(client: TestClient, auth: dict[str, str]) -> None:
    for response in (
        client.get("/api/v1/health/live"),
        client.get("/api/v1/auth/me", headers=auth),
        client.get("/api/v1/watchlists"),  # 401 error envelope
    ):
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["referrer-policy"] == "no-referrer"
        assert response.headers["x-request-id"]


def test_tampered_or_foreign_tokens_are_rejected(client: TestClient, auth: dict[str, str]) -> None:
    token = auth["Authorization"].removeprefix("Bearer ")
    header, payload, signature = token.split(".")
    forged = f"{header}.{payload}.{signature[::-1]}"
    for bad in (forged, "not-a-jwt", f"{header}.{payload}."):
        r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {bad}"})
        assert r.status_code == 401


def test_status_endpoints_do_not_leak_configuration_secrets(
    client: TestClient, auth: dict[str, str], monkeypatch: object
) -> None:
    from app.core.config import get_settings

    secret = "sk-ant-test-" + "z" * 30
    monkeypatch.setenv("FINSIGHT_ANTHROPIC_API_KEY", secret)  # type: ignore[attr-defined]
    get_settings.cache_clear()
    bodies = [
        client.get("/api/v1/research/status", headers=auth).text,
        client.get("/api/v1/market/status", headers=auth).text,
        client.get("/api/v1/health/ready").text,
    ]
    assert all(secret not in body for body in bodies)
    assert "test-secret-" not in "".join(bodies)  # JWT secret from the test env
