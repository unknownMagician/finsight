"""In-memory provider that runs the real EDGAR normalizer on synthetic data (no network)."""

from datetime import UTC, datetime
from typing import Any

from app.providers.base import CompanyListing, IngestionResult, ProviderError
from app.providers.edgar_normalize import normalize_companyfacts
from tests import fixtures_edgar

SYNTH = CompanyListing(
    ticker="SYNW", cik=fixtures_edgar.CIK, name="Synthetic Widgets Inc.", exchange="TEST"
)
OTHER = CompanyListing(ticker="OTHR", cik="0000000099", name="Other Synthetic Co.", exchange=None)


class FakeProvider:
    name = "fake_edgar"

    def __init__(self) -> None:
        self.listings = {SYNTH.ticker: SYNTH, OTHER.ticker: OTHER}
        self.documents: dict[str, dict[str, Any]] = {
            SYNTH.cik: fixtures_edgar.companyfacts(),
            OTHER.cik: {"entityName": OTHER.name, "facts": {}},
        }
        self.fail_with: Exception | None = None
        self.fetch_count = 0

    def list_companies(self) -> list[CompanyListing]:
        return list(self.listings.values())

    def lookup(self, ticker: str) -> CompanyListing | None:
        if self.fail_with:
            raise self.fail_with
        return self.listings.get(ticker.upper())

    def fetch_annual_financials(self, listing: CompanyListing) -> IngestionResult:
        if self.fail_with:
            raise self.fail_with
        self.fetch_count += 1
        doc = self.documents.get(listing.cik)
        if doc is None:
            raise ProviderError("no document")
        normalized = normalize_companyfacts(doc)
        return IngestionResult(
            provider=self.name,
            source_url=f"https://example.test/companyfacts/CIK{listing.cik}.json",
            retrieved_at=datetime(2026, 10, 1, tzinfo=UTC),
            entity_name=normalized.entity_name,
            periods=normalized.periods,
            warnings=normalized.warnings,
        )
