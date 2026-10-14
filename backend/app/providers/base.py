"""Provider-neutral contracts for external financial data sources."""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Protocol

StatementName = Literal["income", "balance", "cash_flow"]


class ProviderError(Exception):
    """The provider failed (network, 5xx, malformed payload)."""


class ProviderNotFoundError(ProviderError):
    """The provider has no data for the requested entity."""


@dataclass(frozen=True)
class CompanyListing:
    ticker: str
    cik: str  # 10-digit zero-padded
    name: str
    exchange: str | None = None


@dataclass(frozen=True)
class IngestedLineItem:
    statement: StatementName
    item: str  # field name on the domain statement model
    value: Decimal
    source_concept: str
    source_accession: str | None


@dataclass(frozen=True)
class IngestedPeriod:
    fiscal_year: int
    fiscal_period: str
    period_start: date | None
    period_end: date
    currency: str
    scale: str
    items: list[IngestedLineItem]


@dataclass(frozen=True)
class IngestionResult:
    provider: str
    source_url: str
    retrieved_at: datetime
    entity_name: str | None
    periods: list[IngestedPeriod]
    warnings: list[str] = field(default_factory=list)


class FinancialDataProvider(Protocol):
    name: str

    def list_companies(self) -> list[CompanyListing]: ...

    def lookup(self, ticker: str) -> CompanyListing | None: ...

    def fetch_annual_financials(self, listing: CompanyListing) -> IngestionResult: ...
