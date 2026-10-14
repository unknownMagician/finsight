from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

API = "/api/v1/calculations"

DCF: dict[str, Any] = {
    "currency": "USD",
    "scale": "millions",
    "free_cash_flows": [100, 110, 121],
    "wacc": "0.10",
    "terminal_method": "perpetuity_growth",
    "terminal_growth": 0.02,
    "net_debt": 200,
    "shares_outstanding": 10,
}


def test_calculators_require_auth(client: TestClient) -> None:
    assert client.post(f"{API}/dcf", json=DCF).status_code == 401


def test_dcf_matches_engine_and_returns_exact_decimals(
    client: TestClient, auth: dict[str, str]
) -> None:
    r = client.post(f"{API}/dcf", json=DCF, headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["enterprise_value"], str)
    assert abs(Decimal(body["enterprise_value"]) - Decimal(15750) / 11) < Decimal("1e-18")
    assert body["terminal_value"] == "1542.75"
    assert [w["code"] for w in body["warnings"]] == ["terminal_value_dominant"]


def test_dcf_rejects_growth_at_or_above_wacc(client: TestClient, auth: dict[str, str]) -> None:
    r = client.post(f"{API}/dcf", json={**DCF, "terminal_growth": "0.10"}, headers=auth)
    assert r.status_code == 422
    error = r.json()["error"]
    assert error["code"] == "validation_error"
    assert "must be below wacc" in error["details"][0]["msg"]


def test_sensitivity(client: TestClient, auth: dict[str, str]) -> None:
    body = {"inputs": DCF, "wacc_values": ["0.02", "0.10"], "column_values": ["0.03"]}
    r = client.post(f"{API}/dcf/sensitivity", json=body, headers=auth)
    assert r.status_code == 200
    table = r.json()
    assert table["cells"][0] == [None]
    assert "0,0" in table["invalid_reasons"]
    too_big = {**body, "wacc_values": ["0.1"] * 16}
    assert client.post(f"{API}/dcf/sensitivity", json=too_big, headers=auth).status_code == 422


def test_wacc(client: TestClient, auth: dict[str, str]) -> None:
    payload = {
        "risk_free_rate": "0.04",
        "equity_risk_premium": "0.05",
        "beta": "1.2",
        "pre_tax_cost_of_debt": "0.06",
        "tax_rate": "0.25",
        "equity_value": 800,
        "debt_value": 200,
    }
    r = client.post(f"{API}/wacc", json=payload, headers=auth)
    assert Decimal(r.json()["wacc"]) == Decimal("0.089")


def test_forecast(client: TestClient, auth: dict[str, str]) -> None:
    base_assumptions = {
        "revenue_growth": ["0.1", "0.1"],
        "ebit_margin": ["0.2", "0.2"],
        "tax_rate": "0.25",
        "da_pct_revenue": "0.05",
        "capex_pct_revenue": "0.06",
        "nwc_pct_revenue": "0.1",
    }
    payload = {
        "base": {"base_year": 2025, "base_revenue": 1000, "currency": "USD", "scale": "millions"},
        "scenarios": {"base": base_assumptions},
    }
    r = client.post(f"{API}/forecast", json=payload, headers=auth)
    assert r.status_code == 200
    years = r.json()["scenarios"]["base"]["years"]
    assert [Decimal(y["free_cash_flow"]) for y in years] == [Decimal(144), Decimal("158.4")]

    no_base = {**payload, "scenarios": {"bull": base_assumptions}}
    r = client.post(f"{API}/forecast", json=no_base, headers=auth)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_assumptions"


def _company(name: str, currency: str = "USD", **fields: Any) -> dict[str, Any]:
    return {"company": name, "currency": currency, "scale": "millions", **fields}


def test_comps(client: TestClient, auth: dict[str, str]) -> None:
    target = _company("T", market_cap=1000, net_debt=200, ebitda=100, shares_outstanding=100)
    peers = [
        _company(f"P{i}", market_cap=1000, enterprise_value=ev, ebitda=100)
        for i, ev in enumerate([1000, 1100, 1200])
    ]
    payload = {"target": target, "peers": peers, "multiples": ["ev_ebitda"]}
    r = client.post(f"{API}/comps", json=payload, headers=auth)
    assert r.status_code == 200
    implied = r.json()["implied"]["ev_ebitda"]
    assert Decimal(implied["implied_value_per_share"]) == 9  # 11x * 100 - 200, / 100

    mixed = {**payload, "peers": [*peers, _company("EU", "EUR", market_cap=1)]}
    r = client.post(f"{API}/comps", json=mixed, headers=auth)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_assumptions"


def test_compute_rate_limit(
    client: TestClient, auth: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import get_settings

    monkeypatch.setenv("FINSIGHT_RATE_LIMIT_COMPUTE_PER_MINUTE", "2")
    get_settings.cache_clear()
    codes = [client.post(f"{API}/dcf", json=DCF, headers=auth).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
