from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

API = "/api/v1/watchlists"

# These suites exercise the optional US market (SEC EDGAR via the fake provider).
pytestmark = pytest.mark.usefixtures("us_market")


@pytest.fixture
def companies(client: TestClient, auth: dict[str, str]) -> None:
    for ticker in ("SYNW", "OTHR"):
        assert client.post(f"/api/v1/companies/{ticker}/ingest", headers=auth).status_code == 200


def test_watchlist_lifecycle(client: TestClient, auth: dict[str, str], companies: None) -> None:
    r = client.post(API, json={"name": "  Tech  "}, headers=auth)
    assert r.status_code == 201
    wl = r.json()
    assert wl["name"] == "Tech" and wl["companies"] == []

    url = f"{API}/{wl['id']}"
    r = client.post(f"{url}/items", json={"ticker": "synw"}, headers=auth)
    assert [c["ticker"] for c in r.json()["companies"]] == ["SYNW"]
    r = client.post(f"{url}/items", json={"ticker": "SYNW"}, headers=auth)  # idempotent
    assert len(r.json()["companies"]) == 1
    client.post(f"{url}/items", json={"ticker": "OTHR"}, headers=auth)

    assert client.patch(url, json={"name": "Watch"}, headers=auth).json()["name"] == "Watch"
    r = client.delete(f"{url}/items/SYNW", headers=auth)
    assert [c["ticker"] for c in r.json()["companies"]] == ["OTHR"]
    assert client.delete(f"{url}/items/SYNW", headers=auth).status_code == 404

    assert [w["name"] for w in client.get(API, headers=auth).json()] == ["Watch"]
    assert client.delete(url, headers=auth).status_code == 204
    assert client.get(url, headers=auth).status_code == 404


def test_validation_and_conflicts(
    client: TestClient, auth: dict[str, str], companies: None
) -> None:
    wl = client.post(API, json={"name": "A"}, headers=auth).json()
    assert client.post(API, json={"name": "A"}, headers=auth).status_code == 409
    assert client.post(API, json={"name": "   "}, headers=auth).status_code == 422
    r = client.post(f"{API}/{wl['id']}/items", json={"ticker": "NOPE"}, headers=auth)
    assert r.status_code == 404 and r.json()["error"]["code"] == "company_not_found"
    assert client.get(f"{API}/not-a-uuid", headers=auth).status_code == 404


def test_users_cannot_access_each_others_watchlists(
    client: TestClient,
    auth: dict[str, str],
    register_and_login: Callable[[str], dict[str, str]],
    companies: None,
) -> None:
    alice_wl = client.post(API, json={"name": "Private"}, headers=auth).json()
    mallory = register_and_login("mallory@example.com")
    url = f"{API}/{alice_wl['id']}"

    assert client.get(API, headers=mallory).json() == []
    assert client.get(url, headers=mallory).status_code == 404
    assert client.patch(url, json={"name": "pwned"}, headers=mallory).status_code == 404
    assert client.post(f"{url}/items", json={"ticker": "SYNW"}, headers=mallory).status_code == 404
    assert client.delete(url, headers=mallory).status_code == 404

    # Alice's watchlist is untouched, and Mallory can reuse the same name independently.
    assert client.get(url, headers=auth).json()["name"] == "Private"
    assert client.post(API, json={"name": "Private"}, headers=mallory).status_code == 201
