"""API request/response schemas (transport layer).

Calculator endpoints reuse the domain models directly (e.g. ``DCFInputs`` / ``DCFResult``), so
the API contract is exactly the validated domain contract. Decimals are serialized as JSON
strings to avoid binary floating-point loss; clients may send numbers or strings.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

from app.domain.comps import CompanyMetrics, Multiple
from app.domain.dcf import DCFInputs, SensitivityOutput
from app.domain.forecast import ForecastAssumptions, ForecastBase, ScenarioName
from app.domain.market_multiples import MarketMultiplesReport
from app.domain.types import ReportingBasis

TICKER_PATTERN = r"^[A-Za-z0-9.&\-]{1,30}$"  # NSE symbols may contain '&' and '-' (M&M)
Ticker = Annotated[
    # The pattern is checked before upper-casing, so it must accept lower case.
    str, StringConstraints(strip_whitespace=True, to_upper=True, pattern=TICKER_PATTERN)
]
Market = Literal["IN", "US"]


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


# --- auth ---------------------------------------------------------------------------------------


class RegisterRequest(Schema):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    display_name: str | None = Field(default=None, min_length=1, max_length=100)


class LoginRequest(Schema):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(Schema):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 - OAuth2 token type, not a secret
    expires_in: int


class UserOut(Schema):
    id: uuid.UUID
    email: str
    display_name: str | None
    created_at: datetime


# --- companies & financials --------------------------------------------------------------------


class InstrumentOut(Schema):
    exchange: str
    symbol: str
    isin: str | None
    series: str | None
    name: str
    currency: str
    listing_status: str
    provider: str
    last_traded_on: date | None
    former_symbols: list[str]
    retrieved_at: datetime


class CompanyOut(Schema):
    market: str
    ticker: str
    name: str
    isin: str | None
    cik: str | None  # US (SEC) only
    exchange: str | None  # US listing venue from the SEC directory
    last_ingested_at: datetime | None
    instruments: list[InstrumentOut] = []


class LineItemOut(Schema):
    statement: str
    item: str
    value: Decimal
    source_concept: str | None
    source_accession: str | None


class SourceOut(Schema):
    provider: str
    url: str | None
    retrieved_at: datetime


class PeriodOut(Schema):
    fiscal_year: int
    fiscal_period: str
    basis: str
    period_start: date | None
    period_end: date
    currency: str
    scale: str
    kind: str
    source: SourceOut
    line_items: list[LineItemOut]


class FinancialsOut(Schema):
    company: CompanyOut
    available_bases: list[str]
    periods: list[PeriodOut]


class IngestOut(Schema):
    company: CompanyOut
    provider: str
    periods_ingested: int
    fiscal_years: list[int]
    warnings: list[str]


# --- market data -------------------------------------------------------------------------------

DataNature = Literal["end_of_day", "delayed", "live", "demo"]


class FreshnessOut(Schema):
    """How current a piece of market data is, and where it came from."""

    provider: str
    nature: DataNature
    as_of: date | None  # trading date the data describes
    retrieved_at: datetime
    cached: bool
    stale: bool
    adjusted: bool | None = None  # prices adjusted for splits/bonuses/dividends?
    source_url: str | None = None


class PriceBarOut(Schema):
    date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int | None
    prev_close: Decimal | None


class PriceHistoryOut(Schema):
    ticker: str
    listing: InstrumentOut
    currency: str
    bars: list[PriceBarOut]
    freshness: FreshnessOut
    warnings: list[str]


class QuoteOut(Schema):
    """The latest available end-of-day bar. Not a real-time quote."""

    ticker: str
    listing: InstrumentOut
    currency: str
    trade_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    prev_close: Decimal | None
    change: Decimal | None
    change_pct: Decimal | None
    volume: int | None
    freshness: FreshnessOut


class CorporateActionOut(Schema):
    exchange: str
    symbol: str
    isin: str | None
    ex_date: date
    record_date: date | None
    action_type: str
    ratio_numerator: int | None
    ratio_denominator: int | None
    cash_amount: Decimal | None
    description: str


class CorporateActionsOut(Schema):
    ticker: str
    provider: str
    retrieved_at: datetime
    cached: bool
    source_urls: list[str]
    actions: list[CorporateActionOut]


class ValuationSnapshotOut(Schema):
    ticker: str
    listing: InstrumentOut
    basis: ReportingBasis
    period_source: SourceOut
    quote: QuoteOut
    report: MarketMultiplesReport


class ProviderInfoOut(Schema):
    role: str
    name: str | None
    configured: bool
    capabilities: list[str]
    data_nature: str | None
    usage_terms: str


class MarketStatusOut(Schema):
    default_market: Market
    providers: list[ProviderInfoOut]
    reachable: bool
    latest_trading_date: date | None
    published_at: datetime | None
    unavailable_capabilities: list[str]


class DirectorySyncOut(Schema):
    provider: str
    as_of: date
    listings: int
    companies_created: int
    instruments_created: int
    renamed: int
    marked_not_in_snapshot: int


# --- calculators -------------------------------------------------------------------------------


class SensitivityRequest(Schema):
    inputs: DCFInputs
    wacc_values: list[Decimal] = Field(min_length=1, max_length=15)
    column_values: list[Decimal] = Field(min_length=1, max_length=15)
    output: SensitivityOutput = "value_per_share"


class ForecastRequest(Schema):
    base: ForecastBase
    scenarios: dict[ScenarioName, ForecastAssumptions]


class CompsRequest(Schema):
    target: CompanyMetrics
    peers: list[CompanyMetrics] = Field(min_length=1, max_length=50)
    multiples: list[Multiple] = Field(default_factory=lambda: list(Multiple), min_length=1)


# --- watchlists --------------------------------------------------------------------------------

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class WatchlistCreate(Schema):
    name: Name


class WatchlistUpdate(Schema):
    name: Name


class WatchlistItemAdd(Schema):
    ticker: Ticker
    market: Market | None = None  # defaults to FINSIGHT_DEFAULT_MARKET


class WatchlistOut(Schema):
    id: uuid.UUID
    name: str
    companies: list[CompanyOut]
    created_at: datetime
    updated_at: datetime


# --- saved valuations --------------------------------------------------------------------------


class SavedValuationCreate(Schema):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    ticker: Ticker | None = None
    market: Market | None = None  # defaults to FINSIGHT_DEFAULT_MARKET
    inputs: DCFInputs


class SavedValuationOut(Schema):
    id: uuid.UUID
    name: str
    ticker: str | None
    market: str | None
    method: str
    engine_version: str
    inputs: DCFInputs
    result: dict[str, object]
    created_at: datetime


# --- documents & AI research --------------------------------------------------------------------


class CompanyRefOut(Schema):
    market: str
    ticker: str
    name: str


class DocumentFactOut(Schema):
    id: int
    metric: str
    value: Decimal
    unit: str
    currency: str | None
    period_label: str | None
    period_end: date | None
    basis: str
    page_number: int
    quote: str
    status: str  # verified | unverified
    verification_note: str | None
    model: str
    extracted_at: datetime
    kind: str = "extracted"  # read by the AI from the page; verified against its text


class DocumentOut(Schema):
    id: uuid.UUID
    title: str
    doc_type: str
    fiscal_year: int | None
    filename: str
    size_bytes: int
    page_count: int
    pages_with_text: int
    status: str  # ready | no_text
    company: CompanyRefOut | None
    facts: list[DocumentFactOut]
    created_at: datetime


class DocumentPageOut(Schema):
    page_number: int
    text: str


class ExtractFactsRequest(Schema):
    metrics: (
        list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=100)]]
        | None
    ) = Field(default=None, max_length=20)


class ResearchAskRequest(Schema):
    question: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=3, max_length=1000)
    ]
    ticker: Ticker | None = None
    market: Market | None = None
    document_ids: list[uuid.UUID] | None = Field(default=None, max_length=10)


class CitationOut(Schema):
    source: int  # 1-based index into ResearchAnswerOut.sources
    cited_text: str
    label: str
    document_id: uuid.UUID | None
    page_number: int | None


class AnswerSegmentOut(Schema):
    text: str
    citations: list[CitationOut]


class ResearchSourceOut(Schema):
    number: int
    title: str
    kind: str  # document_page | financial_data
    document_id: uuid.UUID | None
    page_number: int | None


class GroundingIssueOut(Schema):
    code: str
    segment: int | None
    message: str


class ResearchAnswerOut(Schema):
    question: str
    kind: str = "ai_explanation"
    model: str
    grounding: str  # grounded | partially_grounded | ungrounded
    segments: list[AnswerSegmentOut]
    sources: list[ResearchSourceOut]
    issues: list[GroundingIssueOut]
    input_tokens: int
    output_tokens: int
    disclaimer: str = (
        "AI-generated explanation from the cited sources only. Figures come from the cited "
        "documents or FinSight data; uncited figures are flagged. Not investment advice."
    )


class ResearchStatusOut(Schema):
    configured: bool
    provider: str | None
    model: str | None


# --- research reports -----------------------------------------------------------------------------


class ReportCreate(Schema):
    ticker: Ticker
    market: Market | None = None
    exchange: Literal["NSE", "BSE"] | None = None
    basis: ReportingBasis | None = None
    include_ai: bool = False
    title: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
        | None
    ) = None


class ReportSummaryOut(Schema):
    id: uuid.UUID
    title: str
    ticker: str
    includes_ai: bool
    engine_version: str
    created_at: datetime


class ReportOut(ReportSummaryOut):
    content: dict[str, object]
