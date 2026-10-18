from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.providers.base import ProviderError
from tests import fixtures_edgar
from tests.fakes import FakeProvider

API = "/api/v1/companies"

# These suites exercise the optional US market (SEC EDGAR via the fake provider).
pytestmark = pytest.mark.usefixtures("us_market")


def ingest(client: TestClient, auth: dict[str, str], ticker: str = "SYNW") -> dict[str, object]:
    r = client.post(f"{API}/{ticker}/ingest", headers=auth)
    assert r.status_code == 200, r.text
    body: dict[str, object] = r.json()
    return body


def test_company_endpoints_require_auth(client: TestClient) -> None:
    for path in (f"{API}?q=a", f"{API}/SYNW", f"{API}/SYNW/financials", f"{API}/SYNW/ratios"):
        assert client.get(path).status_code == 401
    assert client.post(f"{API}/SYNW/ingest").status_code == 401


def test_ingest_stores_periods_with_provenance(client: TestClient, auth: dict[str, str]) -> None:
    body = ingest(client, auth, "synw")
    assert body["company"] == {  # type: ignore[comparison-overlap]
        **body["company"],  # type: ignore[dict-item]
        "ticker": "SYNW",
        "cik": fixtures_edgar.CIK,
        "name": "Synthetic Widgets Inc.",
    }
    assert body["fiscal_years"] == [2024, 2023]
    assert len(body["warnings"]) == 1  # type: ignore[arg-type]

    fin = client.get(f"{API}/SYNW/financials", headers=auth).json()
    fy24, fy23 = fin["periods"]
    assert fy24["fiscal_year"] == 2024 and fy24["kind"] == "reported"
    assert fy24["source"]["provider"] == "fake_edgar"
    items = {(i["statement"], i["item"]): i for i in fy24["line_items"]}
    revenue = items[("income", "revenue")]
    assert Decimal(revenue["value"]) == 1000
    assert revenue["source_concept"].startswith("us-gaap:")
    assert revenue["source_accession"] == fixtures_edgar.ACC_2024
    fy23_items = {(i["statement"], i["item"]) for i in fy23["line_items"]}
    assert ("cash_flow", "capital_expenditures") not in fy23_items


def test_reingest_replaces_rather_than_duplicates(
    client: TestClient, auth: dict[str, str], fake_provider: FakeProvider
) -> None:
    ingest(client, auth)
    first = client.get(f"{API}/SYNW/financials", headers=auth).json()
    ingest(client, auth)
    second = client.get(f"{API}/SYNW/financials", headers=auth).json()
    assert fake_provider.fetch_count == 2
    assert [len(p["line_items"]) for p in first["periods"]] == [
        len(p["line_items"]) for p in second["periods"]
    ]


def test_ratios_from_stored_financials(client: TestClient, auth: dict[str, str]) -> None:
    ingest(client, auth)
    report = client.get(f"{API}/SYNW/ratios", headers=auth).json()
    assert report["period"]["fiscal_year"] == 2024
    m = report["metrics"]
    assert Decimal(m["revenue_growth"]["value"]) == Decimal(1000) / Decimal(900) - 1
    assert Decimal(m["return_on_equity"]["value"]) == Decimal(150) / Decimal(850)
    assert Decimal(m["free_cash_flow"]["value"]) == 170
    assert m["gross_margin"]["status"] == "ok"  # derived from revenue - cost_of_revenue
    assert m["current_ratio"]["status"] == "missing_inputs"

    fy23 = client.get(f"{API}/SYNW/ratios", params={"fiscal_year": 2023}, headers=auth).json()
    assert "revenue_growth" not in fy23["metrics"]  # no FY2022 period stored
    assert fy23["metrics"]["free_cash_flow"]["status"] == "missing_inputs"  # capex dropped

    missing = client.get(f"{API}/SYNW/ratios", params={"fiscal_year": 2010}, headers=auth)
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "no_financial_data"


def test_search(client: TestClient, auth: dict[str, str]) -> None:
    ingest(client, auth, "SYNW")
    ingest(client, auth, "OTHR")
    tickers = lambda q: [c["ticker"] for c in client.get(API, params={"q": q}, headers=auth).json()]  # noqa: E731
    assert tickers("synw") == ["SYNW"]
    assert set(tickers("synthetic")) == {"SYNW", "OTHR"}
    assert tickers("zzz") == []
    assert tickers("%") == []  # LIKE wildcards are escaped
    assert client.get(API, params={"q": ""}, headers=auth).status_code == 422


def test_company_without_annual_data(client: TestClient, auth: dict[str, str]) -> None:
    body = ingest(client, auth, "OTHR")
    assert body["periods_ingested"] == 0
    r = client.get(f"{API}/OTHR/ratios", headers=auth)
    assert r.status_code == 404


@pytest.mark.parametrize(
    ("ticker", "error", "status", "code"),
    [
        ("NOPE", None, 404, "company_not_found"),
        ("SYNW", ProviderError("timeout"), 502, "provider_unavailable"),
    ],
)
def test_ingest_errors(
    client: TestClient,
    auth: dict[str, str],
    fake_provider: FakeProvider,
    ticker: str,
    error: Exception | None,
    status: int,
    code: str,
) -> None:
    fake_provider.fail_with = error
    r = client.post(f"{API}/{ticker}/ingest", headers=auth)
    assert r.status_code == status
    assert r.json()["error"]["code"] == code
    assert "timeout" not in r.text  # provider internals are not leaked


def test_ingest_without_configured_provider(client: TestClient, auth: dict[str, str]) -> None:
    client.app.state.provider = None  # type: ignore[attr-defined]
    r = client.post(f"{API}/SYNW/ingest", headers=auth)
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "provider_not_configured"


def test_unknown_company_and_bad_ticker(client: TestClient, auth: dict[str, str]) -> None:
    assert client.get(f"{API}/NOPE", headers=auth).status_code == 404
    assert client.get(f"{API}/bad%20ticker", headers=auth).status_code == 422
