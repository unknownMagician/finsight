"""EDGAR normalizer (pure) and HTTP client (MockTransport, no network)."""

import json
from decimal import Decimal
from typing import Any

import httpx
import pytest

from app.providers.base import CompanyListing, ProviderError, ProviderNotFoundError
from app.providers.edgar_normalize import normalize_companyfacts
from app.providers.sec_edgar import FACTS_URL, TICKERS_URL, SecEdgarProvider, normalize_ticker
from tests import fixtures_edgar

# --- normalizer --------------------------------------------------------------------------------


@pytest.fixture
def normalized() -> Any:
    return normalize_companyfacts(fixtures_edgar.companyfacts())


def _items(period: Any) -> dict[str, Any]:
    return {f"{i.statement}.{i.item}": i for i in period.items}


def test_discovers_only_primary_fiscal_periods(normalized: Any) -> None:
    assert normalized.entity_name == "Synthetic Widgets Inc."
    assert [(p.fiscal_year, str(p.period_end)) for p in normalized.periods] == [
        (2024, "2024-09-28"),
        (2023, "2023-09-30"),
    ]
    assert str(normalized.periods[0].period_start) == "2023-10-01"
    assert {(p.currency, p.scale) for p in normalized.periods} == {("USD", "units")}


def test_restated_value_from_latest_filing_wins(normalized: Any) -> None:
    fy23 = _items(normalized.periods[1])["income.revenue"]
    assert fy23.value == Decimal(900)
    assert fy23.source_accession == fixtures_edgar.ACC_2024


def test_preferred_concept_and_provenance(normalized: Any) -> None:
    revenue = _items(normalized.periods[0])["income.revenue"]
    assert revenue.value == Decimal(1000)  # not the Q4-only 300, not SalesRevenueNet 999
    assert revenue.source_concept == "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax"


def test_instant_and_unit_specific_items(normalized: Any) -> None:
    items = _items(normalized.periods[0])
    assert items["balance.total_assets"].value == Decimal(2000)
    assert items["balance.shares_outstanding"].value == Decimal(100)
    assert items["income.diluted_eps"].value == Decimal("1.5")


def test_sign_violations_dropped_with_warning(normalized: Any) -> None:
    assert "cash_flow.capital_expenditures" not in _items(normalized.periods[1])
    assert "cash_flow.capital_expenditures" in _items(normalized.periods[0])
    (warning,) = normalized.warnings
    assert "FY2023" in warning and "capital_expenditures" in warning


def test_nothing_is_invented(normalized: Any) -> None:
    items = _items(normalized.periods[0])
    assert "income.gross_profit" not in items  # not reported -> not derived here
    assert "balance.inventory" not in items


def test_empty_document() -> None:
    result = normalize_companyfacts({"entityName": "X", "facts": {}})
    assert result.periods == []
    assert result.warnings == ["no us-gaap facts in document"]


# --- HTTP client -------------------------------------------------------------------------------

DIRECTORY = {
    "fields": ["cik", "name", "ticker", "exchange"],
    "data": [[42, "Synthetic Widgets Inc.", "synw", "Nasdaq"], [7, "Dot Co", "brk-b", None]],
}


def provider_with(handler: Any, sleeps: list[float] | None = None) -> SecEdgarProvider:
    return SecEdgarProvider(
        "FinSight tests test@example.com",
        transport=httpx.MockTransport(handler),
        sleep=(sleeps.append if sleeps is not None else lambda _: None),
    )


def test_user_agent_is_required() -> None:
    with pytest.raises(ValueError):
        SecEdgarProvider("  ")


def test_directory_lookup_and_headers() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=DIRECTORY)

    provider = provider_with(handler)
    listing = provider.lookup("synw")
    assert listing == CompanyListing("SYNW", "0000000042", "Synthetic Widgets Inc.", "Nasdaq")
    assert provider.lookup("BRK-B") is not None
    assert provider.lookup("nope") is None
    assert provider.lookup("bad ticker!") is None
    assert len(seen) == 1  # directory cached
    assert str(seen[0].url) == TICKERS_URL
    assert seen[0].headers["User-Agent"] == "FinSight tests test@example.com"


def test_retries_transient_errors_then_succeeds() -> None:
    responses = iter(
        [
            httpx.Response(503),
            httpx.Response(429, headers={"Retry-After": "3"}),
            httpx.Response(200, json=fixtures_edgar.companyfacts()),
        ]
    )
    sleeps: list[float] = []
    provider = provider_with(lambda _: next(responses), sleeps)
    listing = CompanyListing("SYNW", "0000000042", "Synthetic Widgets Inc.")
    result = provider.fetch_annual_financials(listing)
    assert sleeps == [0.5, 3.0]
    assert result.provider == "sec_edgar"
    assert result.source_url == FACTS_URL.format(cik="0000000042")
    assert [p.fiscal_year for p in result.periods] == [2024, 2023]


def test_gives_up_after_max_retries() -> None:
    sleeps: list[float] = []
    provider = provider_with(lambda _: httpx.Response(500), sleeps)
    with pytest.raises(ProviderError, match="500"):
        provider.fetch_annual_financials(CompanyListing("X", "0000000001", "X"))
    assert sleeps == [0.5, 1.0, 2.0]


def test_transport_errors_are_retried_then_wrapped() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    with pytest.raises(ProviderError, match="unreachable"):
        provider_with(handler).fetch_annual_financials(CompanyListing("X", "0000000001", "X"))


def test_not_found_and_malformed() -> None:
    with pytest.raises(ProviderNotFoundError):
        provider_with(lambda _: httpx.Response(404)).fetch_annual_financials(
            CompanyListing("X", "0000000001", "X")
        )
    with pytest.raises(ProviderError, match="malformed"):
        provider_with(lambda _: httpx.Response(200, content=b"<html>")).lookup("X")
    with pytest.raises(ProviderError, match="directory format"):
        provider_with(lambda _: httpx.Response(200, content=json.dumps({"x": 1}))).lookup("X")


@pytest.mark.parametrize(
    ("raw", "expected"), [(" aapl ", "AAPL"), ("BRK.B", "BRK.B"), ("a b", None), ("", None)]
)
def test_normalize_ticker(raw: str, expected: str | None) -> None:
    assert normalize_ticker(raw) == expected
