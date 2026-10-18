from collections.abc import Callable
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from tests.test_calculations_api import DCF

API = "/api/v1/valuations"

# These suites exercise the optional US market (SEC EDGAR via the fake provider).
pytestmark = pytest.mark.usefixtures("us_market")


def test_save_list_get_delete(client: TestClient, auth: dict[str, str]) -> None:
    client.post("/api/v1/companies/SYNW/ingest", headers=auth)
    r = client.post(API, json={"name": "Base case", "ticker": "synw", "inputs": DCF}, headers=auth)
    assert r.status_code == 201, r.text
    saved = r.json()
    assert saved["ticker"] == "SYNW" and saved["method"] == "dcf"
    assert abs(Decimal(saved["result"]["enterprise_value"]) - Decimal(15750) / 11) < Decimal(
        "1e-18"
    )
    assert saved["inputs"]["wacc"] == "0.10"  # stored exactly as given

    assert [v["id"] for v in client.get(API, headers=auth).json()] == [saved["id"]]
    assert client.get(f"{API}/{saved['id']}", headers=auth).json() == saved
    assert client.delete(f"{API}/{saved['id']}", headers=auth).status_code == 204
    assert client.get(f"{API}/{saved['id']}", headers=auth).status_code == 404


def test_client_cannot_supply_results(client: TestClient, auth: dict[str, str]) -> None:
    payload = {"name": "x", "inputs": DCF, "result": {"enterprise_value": "999999"}}
    assert client.post(API, json=payload, headers=auth).status_code == 422


def test_invalid_inputs_and_unknown_company(client: TestClient, auth: dict[str, str]) -> None:
    bad = {"name": "x", "inputs": {**DCF, "terminal_growth": "0.2"}}
    assert client.post(API, json=bad, headers=auth).status_code == 422
    r = client.post(API, json={"name": "x", "ticker": "NOPE", "inputs": DCF}, headers=auth)
    assert r.status_code == 404


def test_valuations_are_private(
    client: TestClient, auth: dict[str, str], register_and_login: Callable[[str], dict[str, str]]
) -> None:
    saved = client.post(API, json={"name": "Mine", "inputs": DCF}, headers=auth).json()
    eve = register_and_login("eve@example.com")
    assert client.get(API, headers=eve).json() == []
    assert client.get(f"{API}/{saved['id']}", headers=eve).status_code == 404
    assert client.delete(f"{API}/{saved['id']}", headers=eve).status_code == 404
    assert client.get(f"{API}/{saved['id']}", headers=auth).status_code == 200
