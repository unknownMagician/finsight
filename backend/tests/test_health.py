from fastapi.testclient import TestClient

from app import __version__


def test_liveness(client: TestClient) -> None:
    response = client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "FinSight API",
        "version": __version__,
        "environment": "test",
    }


def test_readiness_ok(client: TestClient) -> None:
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"database": "ok"}}


def test_readiness_reports_unavailable_when_db_down(client: TestClient, monkeypatch) -> None:
    def boom(_session: object) -> None:
        raise RuntimeError("db down")

    monkeypatch.setattr("app.api.health.check_database", boom)
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "checks": {"database": "error"}}


def test_request_id_is_generated(client: TestClient) -> None:
    response = client.get("/api/v1/health/live")
    assert len(response.headers["x-request-id"]) == 32


def test_safe_request_id_is_echoed(client: TestClient) -> None:
    response = client.get("/api/v1/health/live", headers={"X-Request-ID": "abc-123"})
    assert response.headers["x-request-id"] == "abc-123"


def test_unsafe_request_id_is_replaced(client: TestClient) -> None:
    response = client.get("/api/v1/health/live", headers={"X-Request-ID": "bad id\nwith newline"})
    assert response.headers["x-request-id"] != "bad id\nwith newline"
    assert len(response.headers["x-request-id"]) == 32


def test_unknown_route_uses_error_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "http_error"
    assert body["error"]["request_id"] == response.headers["x-request-id"]
    assert len(response.headers.get_list("x-request-id")) == 1


def test_unhandled_exception_does_not_leak_details(client: TestClient) -> None:
    @client.app.get("/api/v1/_boom")  # type: ignore[attr-defined]
    def _boom() -> None:
        raise RuntimeError("secret internal detail")

    response = client.get("/api/v1/_boom")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "secret" not in response.text
    assert response.json()["error"]["request_id"] == response.headers["x-request-id"]


def test_validation_error_envelope(client: TestClient) -> None:
    @client.app.get("/api/v1/_typed")  # type: ignore[attr-defined]
    def _typed(n: int) -> dict[str, int]:
        return {"n": n}

    response = client.get("/api/v1/_typed", params={"n": "not-a-number"})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["details"][0]["loc"] == ["query", "n"]
