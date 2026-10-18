"""Provider-neutral contracts for external financial data sources.

Two families of providers:

- ``FinancialDataProvider``: the original US contract (SEC EDGAR). Companies are identified by
  ticker + CIK and only annual statements are returned.
- ``MarketDataProvider`` / ``FundamentalsProvider``: the India-first contracts. Instruments are
  exchange-specific listings (NSE/BSE) grouped into companies by ISIN; prices are end-of-day
  bars; statements carry a period type (annual/quarterly) and a reporting basis.

Providers return DTOs, never ORM objects, and never fill gaps: a value the source does not
provide is absent, and a capability the source does not offer raises
``CapabilityUnavailableError``.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal, Protocol

from app.domain.types import ReportingBasis

StatementName = Literal["income", "balance", "cash_flow"]


class ProviderError(Exception):
    """The provider failed (network, 5xx, malformed payload)."""


class ProviderNotFoundError(ProviderError):
    """The provider has no data for the requested entity."""


class ProviderRateLimitedError(ProviderError):
    """The provider refused the request because a rate limit or quota was exhausted."""


class CapabilityUnavailableError(ProviderError):
    """The configured provider does not offer this kind of data (e.g. shareholding)."""


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
    fiscal_period: str  # FY, Q1..Q4
    period_start: date | None
    period_end: date
    currency: str
    scale: str
    items: list[IngestedLineItem]
    basis: ReportingBasis = "unspecified"


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


# --- India-first market data contracts ----------------------------------------------------------


class Capability(StrEnum):
    INSTRUMENT_DIRECTORY = "instrument_directory"
    EOD_PRICES = "eod_prices"
    INTRADAY_PRICES = "intraday_prices"
    CORPORATE_ACTIONS = "corporate_actions"
    FINANCIAL_STATEMENTS = "financial_statements"
    SHAREHOLDING = "shareholding"
    ANNOUNCEMENTS = "announcements"


Exchange = Literal["NSE", "BSE"]


@dataclass(frozen=True)
class InstrumentListing:
    """One exchange-specific listing, exactly as the provider reports it."""

    exchange: Exchange
    symbol: str
    name: str
    isin: str | None  # only ever a real ISIN supplied by the source; never synthesized
    series: str | None  # NSE series (EQ, BE, ...) or BSE group (A, B, T, ...)
    # Groups listings of the same company across exchanges. The ISIN when the source has one;
    # otherwise a provider-scoped key (the demo provider uses "demo:<n>").
    company_key: str
    currency: str = "INR"
    provider_instrument_key: str | None = None
    last_traded_on: date | None = None  # trading date of the snapshot the listing came from


@dataclass(frozen=True)
class DirectoryResult:
    provider: str
    listings: list[InstrumentListing]
    as_of: date  # trading date of the snapshot
    retrieved_at: datetime
    source_urls: list[str]


@dataclass(frozen=True)
class PriceBar:
    """One end-of-day bar in the listing's currency (major units, e.g. rupees)."""

    date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int | None
    prev_close: Decimal | None = None
    turnover: Decimal | None = None
    trades: int | None = None


DataNature = Literal["end_of_day", "delayed", "live", "demo"]


@dataclass(frozen=True)
class PriceSeries:
    provider: str
    exchange: Exchange
    symbol: str
    currency: str
    nature: DataNature
    adjusted: bool  # False: raw bhavcopy prices, not adjusted for splits/bonuses/dividends
    bars: list[PriceBar]  # ascending by date
    retrieved_at: datetime
    source_url: str | None
    warnings: list[str] = field(default_factory=list)


CorporateActionType = Literal["dividend", "split", "bonus", "rights", "merger", "other"]


@dataclass(frozen=True)
class CorporateAction:
    exchange: Exchange
    symbol: str
    isin: str | None
    ex_date: date
    record_date: date | None
    action_type: CorporateActionType
    ratio_numerator: int | None
    ratio_denominator: int | None
    cash_amount: Decimal | None  # per share, in rupees
    face_value_from: Decimal | None
    face_value_to: Decimal | None
    description: str  # original announcement text


@dataclass(frozen=True)
class CorporateActionsResult:
    provider: str
    actions: list[CorporateAction]
    retrieved_at: datetime
    source_url: str | None


@dataclass(frozen=True)
class ProviderStatus:
    provider: str
    reachable: bool
    latest_trading_date: date | None
    published_at: datetime | None
    detail: str | None = None


class MarketDataProvider(Protocol):
    name: str
    capabilities: frozenset[Capability]

    def fetch_directory(self) -> DirectoryResult: ...

    def fetch_eod_bars(
        self, exchange: Exchange, symbol: str, start: date, end: date
    ) -> PriceSeries: ...

    def fetch_corporate_actions(self, symbol: str) -> CorporateActionsResult: ...

    def status(self) -> ProviderStatus: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class InstrumentRef:
    """What a fundamentals provider needs to find a company's statements."""

    exchange: Exchange
    symbol: str
    isin: str | None
    name: str


class FundamentalsProvider(Protocol):
    name: str
    capabilities: frozenset[Capability]

    def fetch_financials(self, ref: InstrumentRef) -> IngestionResult: ...

    def close(self) -> None: ...
