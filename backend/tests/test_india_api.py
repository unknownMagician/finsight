"""India-first API journey against the deterministic demo provider (no network, no keys)."""

from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.providers.base import (
    Capability,
    CapabilityUnavailableError,
    PriceSeries,
    ProviderRateLimitedError,
)
from app.providers.demo import DemoMarketDataProvider
from tests.conftest import DEMO_TODAY

API = "/api/v1/companies"


def get(client: TestClient, auth: dict[str, str], path: str, **params: Any) -> Any:
    r = client.get(f"{API}{path}", params=params, headers=auth)
    assert r.status_code == 200, r.text
    return r.json()


def market_status(client: TestClient, auth: dict[str, str]) -> Any:
    r = client.get("/api/v1/market/status", headers=auth)
    assert r.status_code == 200, r.text
    return r.json()


def ingest(client: TestClient, auth: dict[str, str], ticker: str) -> Any:
    r = client.post(f"{API}/{ticker}/ingest", headers=auth)
    assert r.status_code == 200, r.text
    return r.json()


def test_new_endpoints_require_auth(client: TestClient) -> None:
    for path in (
        f"{API}/DEMOINFO/quote",
        f"{API}/DEMOINFO/prices",
        f"{API}/DEMOINFO/corporate-actions",
        f"{API}/DEMOINFO/valuation-snapshot",
        "/api/v1/market/status",
    ):
        assert client.get(path).status_code == 401
    assert client.post("/api/v1/market/directory/sync").status_code == 401


def test_search_defaults_to_india_and_groups_listings(
    client: TestClient, auth: dict[str, str]
) -> None:
    results = get(client, auth, "", q="demo")  # first search loads the demo directory
    tickers = {c["ticker"]: c for c in results}
    assert set(tickers) == {"DEMOINFO", "DEMOSTEEL", "DEMOBANK", "DEMOAGRO", "DEMOAGRO.BSE"}
    info = tickers["DEMOINFO"]
    assert info["market"] == "IN" and info["isin"] is None and info["cik"] is None
    assert {(i["exchange"], i["symbol"]) for i in info["instruments"]} == {
        ("BSE", "DEMOINFO"),
        ("NSE", "DEMOINFO"),
    }
    assert {i["provider"] for i in info["instruments"]} == {"demo"}
    # Same symbol on two exchanges, two different companies: never merged by symbol.
    assert tickers["DEMOAGRO"]["name"] == "Demo Agro Industries Ltd"
    assert tickers["DEMOAGRO.BSE"]["name"] == "Demo Agrochem Traders Ltd"

    bse_only = get(client, auth, "", q="demo", exchange="BSE")
    assert {c["ticker"] for c in bse_only} == {"DEMOINFO", "DEMOBANK", "DEMOAGRO.BSE"}
    assert get(client, auth, "", q="steel")[0]["ticker"] == "DEMOSTEEL"
    us = client.get(API, params={"q": "demo", "market": "US"}, headers=auth)
    assert us.status_code == 200 and us.json() == []  # markets are separate


def test_quote_requires_unambiguous_listing(client: TestClient, auth: dict[str, str]) -> None:
    get(client, auth, "", q="demo")
    r = client.get(f"{API}/DEMOINFO/quote", headers=auth)
    assert r.status_code == 409
    err = r.json()["error"]
    assert err["code"] == "ambiguous_listing"
    assert {x["exchange"] for x in err["details"]["listings"]} == {"NSE", "BSE"}

    nse = get(client, auth, "/DEMOINFO/quote", exchange="NSE")
    bse = get(client, auth, "/DEMOINFO/quote", exchange="BSE")
    assert nse["listing"]["exchange"] == "NSE" and bse["listing"]["exchange"] == "BSE"
    assert nse["close"] != bse["close"]  # separate instruments, separate prices
    assert nse["trade_date"] == "2026-10-16" and nse["currency"] == "INR"
    fresh = nse["freshness"]
    assert fresh["provider"] == "demo" and fresh["nature"] == "demo"
    assert fresh["stale"] is False and fresh["adjusted"] is False and fresh["cached"] is False
    assert Decimal(nse["change"]) == Decimal(nse["close"]) - Decimal(nse["prev_close"])

    again = get(client, auth, "/DEMOINFO/quote", exchange="NSE")
    assert again["freshness"]["cached"] is True and again["close"] == nse["close"]

    # Single-listing companies need no exchange; a wrong exchange is a clear 404.
    assert get(client, auth, "/DEMOBANK/quote")["listing"]["exchange"] == "BSE"
    r = client.get(f"{API}/DEMOBANK/quote", params={"exchange": "NSE"}, headers=auth)
    assert r.status_code == 404 and r.json()["error"]["code"] == "listing_not_found"


def test_price_history(client: TestClient, auth: dict[str, str]) -> None:
    get(client, auth, "", q="demo")
    body = get(
        client, auth, "/DEMOSTEEL/prices", start="2026-10-01", end="2026-10-16", exchange="NSE"
    )
    dates = [b["date"] for b in body["bars"]]
    assert dates[0] == "2026-10-01" and dates[-1] == "2026-10-16" and len(dates) == 12
    assert body["freshness"]["as_of"] == "2026-10-16" and body["currency"] == "INR"
    default = get(client, auth, "/DEMOSTEEL/prices")
    assert default["bars"][0]["date"] >= "2025-10-19"  # default: trailing 365 days

    bad = client.get(
        f"{API}/DEMOSTEEL/prices", params={"start": "2026-10-10", "end": "2026-10-01"}, headers=auth
    )
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "invalid_range"


def test_stale_data_is_flagged(client: TestClient, auth: dict[str, str]) -> None:
    get(client, auth, "", q="demo")
    client.app.state.today = lambda: date(2026, 10, 30)  # type: ignore[attr-defined]
    client.app.state.market_provider = DemoMarketDataProvider(lambda: DEMO_TODAY)  # type: ignore[attr-defined]
    quote = get(client, auth, "/DEMOSTEEL/quote")
    assert quote["trade_date"] == "2026-10-16" and quote["freshness"]["stale"] is True


def test_financials_quarterly_annual_and_basis(client: TestClient, auth: dict[str, str]) -> None:
    get(client, auth, "", q="demo")
    body = ingest(client, auth, "DEMOINFO")
    assert body["provider"] == "demo" and body["fiscal_years"][0] == 2027
    assert "synthetic demo data" in body["warnings"][0]

    fin = get(client, auth, "/DEMOINFO/financials")
    assert fin["available_bases"] == ["consolidated", "standalone"]
    annual = get(client, auth, "/DEMOINFO/financials", period_type="annual", basis="standalone")
    assert {(p["fiscal_period"], p["basis"]) for p in annual["periods"]} == {("FY", "standalone")}
    assert [p["fiscal_year"] for p in annual["periods"]] == [2026, 2025, 2024, 2023, 2022]
    quarterly = get(client, auth, "/DEMOINFO/financials", period_type="quarterly")
    assert {(p["fiscal_year"], p["fiscal_period"]) for p in quarterly["periods"]} == {(2027, "Q1")}
    p = annual["periods"][0]
    assert (p["currency"], p["scale"], p["source"]["provider"]) == ("INR", "crores", "demo")
    items = {i["item"]: i for i in p["line_items"]}
    assert items["revenue"]["source_concept"] == "demo:revenue"

    # Re-ingest replaces rather than duplicates (unique on year, period and basis).
    ingest(client, auth, "DEMOINFO")
    assert len(get(client, auth, "/DEMOINFO/financials")["periods"]) == len(fin["periods"])


def test_ratios_never_mix_bases(client: TestClient, auth: dict[str, str]) -> None:
    get(client, auth, "", q="demo")
    ingest(client, auth, "DEMOINFO")
    consolidated = get(client, auth, "/DEMOINFO/ratios")
    standalone = get(client, auth, "/DEMOINFO/ratios", basis="standalone")
    assert consolidated["basis"] == "consolidated" and standalone["basis"] == "standalone"
    for report in (consolidated, standalone):
        growth = Decimal(report["metrics"]["revenue_growth"]["value"])
        # 10% growth on the same basis (demo amounts are rounded to 0.01 crore)
        assert abs(growth - Decimal("0.10")) < Decimal("1e-6")
    assert consolidated["metrics"]["return_on_capital_employed"]["status"] == "ok"

    ingest(client, auth, "DEMOBANK")
    r = client.get(f"{API}/DEMOBANK/ratios", params={"basis": "consolidated"}, headers=auth)
    assert r.status_code == 404 and "available: standalone" in r.json()["error"]["message"]


def test_valuation_snapshot(client: TestClient, auth: dict[str, str]) -> None:
    get(client, auth, "", q="demo")
    ingest(client, auth, "DEMOINFO")
    snap = get(client, auth, "/DEMOINFO/valuation-snapshot", exchange="NSE")
    close = Decimal(snap["quote"]["close"])
    m = snap["report"]["metrics"]
    assert snap["basis"] == "consolidated" and snap["report"]["period"]["fiscal_year"] == 2026
    eps = Decimal(12000) * Decimal("0.18") * Decimal(10) ** 7 / 400_000_000  # ₹54
    assert abs(Decimal(m["price_to_earnings"]["value"]) - close / eps) < Decimal("1e-6")
    assert Decimal(m["market_cap"]["value"]) == close * 400_000_000 / Decimal(10) ** 7  # crores
    assert Decimal(m["dividend_yield"]["value"]) == Decimal(18) / close  # one ₹18 NSE dividend
    assert snap["report"]["issues"] == []
    assert snap["period_source"]["provider"] == "demo"

    ingest(client, auth, "DEMOSTEEL")
    steel = get(client, auth, "/DEMOSTEEL/valuation-snapshot")["report"]["metrics"]
    assert steel["price_to_earnings"]["status"] == "not_meaningful"  # loss-making year

    ingest(client, auth, "DEMOAGRO")
    agro = get(client, auth, "/DEMOAGRO/valuation-snapshot")["report"]
    assert agro["metrics"]["market_cap"]["status"] == "not_meaningful"  # bonus after FY end
    assert [i["code"] for i in agro["issues"]] == ["share_count_changed_after_period"]

    r = client.get(f"{API}/DEMOBANK/valuation-snapshot", headers=auth)
    assert r.status_code == 404 and r.json()["error"]["code"] == "no_financial_data"


def test_corporate_actions_match_the_company_not_the_symbol(
    client: TestClient, auth: dict[str, str]
) -> None:
    get(client, auth, "", q="demo")
    agro = get(client, auth, "/DEMOAGRO/corporate-actions")
    assert [(a["exchange"], a["action_type"]) for a in agro["actions"]] == [("NSE", "bonus")]
    other = get(client, auth, "/DEMOAGRO.BSE/corporate-actions")
    assert other["actions"] == []  # same symbol on BSE belongs to a different company
    info = get(client, auth, "/DEMOINFO/corporate-actions")
    assert {a["exchange"] for a in info["actions"]} == {"NSE", "BSE"}
    assert info["provider"] == "demo"


class LimitedProvider(DemoMarketDataProvider):
    """Demo data but without corporate actions, and optionally rate-limited prices."""

    capabilities = frozenset({Capability.INSTRUMENT_DIRECTORY, Capability.EOD_PRICES})

    def __init__(self, rate_limited: bool = False) -> None:
        super().__init__(lambda: DEMO_TODAY)
        self.rate_limited = rate_limited
        self.bar_calls = 0

    def fetch_eod_bars(self, *args: Any, **kwargs: Any) -> PriceSeries:
        self.bar_calls += 1
        if self.rate_limited:
            raise ProviderRateLimitedError("quota")
        return super().fetch_eod_bars(*args, **kwargs)

    def fetch_corporate_actions(self, symbol: str) -> Any:
        raise CapabilityUnavailableError("no actions")


def test_unsupported_capabilities_are_explicit(client: TestClient, auth: dict[str, str]) -> None:
    get(client, auth, "", q="demo")
    ingest(client, auth, "DEMOINFO")
    client.app.state.market_provider = LimitedProvider()  # type: ignore[attr-defined]
    r = client.get(f"{API}/DEMOINFO/corporate-actions", headers=auth)
    assert r.status_code == 501 and r.json()["error"]["code"] == "capability_unavailable"

    snap = get(client, auth, "/DEMOINFO/valuation-snapshot", exchange="NSE")["report"]
    assert snap["metrics"]["dividend_yield"]["status"] == "missing_inputs"
    assert [i["code"] for i in snap["issues"]] == ["corporate_actions_unavailable"]

    status = market_status(client, auth)
    assert "corporate_actions" in status["unavailable_capabilities"]
    assert "shareholding" in status["unavailable_capabilities"]


def test_provider_rate_limits_surface_as_503(client: TestClient, auth: dict[str, str]) -> None:
    get(client, auth, "", q="demo")
    provider = LimitedProvider(rate_limited=True)
    client.app.state.market_provider = provider  # type: ignore[attr-defined]
    r = client.get(f"{API}/DEMOSTEEL/quote", headers=auth)
    assert r.status_code == 503 and r.json()["error"]["code"] == "provider_rate_limited"
    assert "quota" not in r.text  # provider internals are not leaked


def test_market_data_rate_limit(
    client: TestClient, auth: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import get_settings

    get(client, auth, "", q="demo")
    monkeypatch.setenv("FINSIGHT_RATE_LIMIT_MARKET_DATA_PER_MINUTE", "2")
    get_settings.cache_clear()
    assert client.get(f"{API}/DEMOSTEEL/quote", headers=auth).status_code == 200
    assert client.get(f"{API}/DEMOSTEEL/quote", headers=auth).status_code == 200
    r = client.get(f"{API}/DEMOSTEEL/quote", headers=auth)
    assert r.status_code == 429 and "Retry-After" in r.headers


def test_fundamentals_can_be_disabled(
    client: TestClient, auth: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import get_settings

    get(client, auth, "", q="demo")
    monkeypatch.setenv("FINSIGHT_FUNDAMENTALS_PROVIDER", "none")
    get_settings.cache_clear()
    r = client.post(f"{API}/DEMOINFO/ingest", headers=auth)
    assert r.status_code == 503 and r.json()["error"]["code"] == "provider_not_configured"
    providers = {p["role"]: p for p in market_status(client, auth)["providers"]}
    assert providers["fundamentals_in"]["configured"] is False
    assert "financial_statements" in market_status(client, auth)["unavailable_capabilities"]


def test_market_status_and_directory_sync(client: TestClient, auth: dict[str, str]) -> None:
    status = market_status(client, auth)
    assert status["default_market"] == "IN"
    assert status["latest_trading_date"] == "2026-10-16" and status["reachable"] is True
    roles = {p["role"]: p for p in status["providers"]}
    assert roles["market_data"]["name"] == "demo" and roles["market_data"]["data_nature"] == "demo"
    assert roles["fundamentals_us"]["configured"] is False  # no SEC user agent in tests
    assert "intraday_prices" in status["unavailable_capabilities"]

    r = client.post("/api/v1/market/directory/sync", headers=auth)
    assert r.status_code == 200 and r.json()["listings"] == 6
    again = client.post("/api/v1/market/directory/sync", headers=auth).json()
    assert again["companies_created"] == 0 and again["instruments_created"] == 0


def test_indian_watchlist_and_valuation_link(
    client: TestClient,
    auth: dict[str, str],
    register_and_login: Callable[[str], dict[str, str]],
) -> None:
    get(client, auth, "", q="demo")
    wl = client.post("/api/v1/watchlists", json={"name": "India"}, headers=auth).json()
    url = f"/api/v1/watchlists/{wl['id']}"
    r = client.post(f"{url}/items", json={"ticker": "m&m"}, headers=auth)
    assert r.status_code == 404  # unknown Indian ticker ('&' is allowed in the pattern)
    r = client.post(f"{url}/items", json={"ticker": "demoinfo"}, headers=auth)
    assert [(c["ticker"], c["market"]) for c in r.json()["companies"]] == [("DEMOINFO", "IN")]
    r = client.post(f"{url}/items", json={"ticker": "DEMOINFO", "market": "US"}, headers=auth)
    assert r.status_code == 404  # the same ticker in another market is another company

    mallory = register_and_login("mallory@example.com")
    assert client.get(url, headers=mallory).status_code == 404
    r = client.delete(f"{url}/items/DEMOINFO", headers=auth)
    assert r.json()["companies"] == []

    from tests.test_calculations_api import DCF

    saved = client.post(
        "/api/v1/valuations", json={"name": "x", "ticker": "DEMOINFO", "inputs": DCF}, headers=auth
    ).json()
    assert (saved["ticker"], saved["market"]) == ("DEMOINFO", "IN")
