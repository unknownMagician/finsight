"""API request/response schemas (transport layer).

Calculator endpoints reuse the domain models directly (e.g. ``DCFInputs`` / ``DCFResult``), so
the API contract is exactly the validated domain contract. Decimals are serialized as JSON
strings to avoid binary floating-point loss; clients may send numbers or strings.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

from app.domain.comps import CompanyMetrics, Multiple
from app.domain.dcf import DCFInputs, SensitivityOutput
from app.domain.forecast import ForecastAssumptions, ForecastBase, ScenarioName

Ticker = Annotated[
    # The pattern is checked before upper-casing, so it must accept lower case.
    str, StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"^[A-Za-z0-9.\-]{1,20}$")
]


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


class CompanyOut(Schema):
    ticker: str
    cik: str
    name: str
    exchange: str | None
    last_ingested_at: datetime | None


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
    period_start: date | None
    period_end: date
    currency: str
    scale: str
    kind: str
    source: SourceOut
    line_items: list[LineItemOut]


class FinancialsOut(Schema):
    company: CompanyOut
    periods: list[PeriodOut]


class IngestOut(Schema):
    company: CompanyOut
    periods_ingested: int
    fiscal_years: list[int]
    warnings: list[str]


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
    inputs: DCFInputs


class SavedValuationOut(Schema):
    id: uuid.UUID
    name: str
    ticker: str | None
    method: str
    engine_version: str
    inputs: DCFInputs
    result: dict[str, object]
    created_at: datetime
