"""Shared domain value types: currency, scale, provenance, reporting periods, issues."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

CurrencyCode = Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]
"""ISO 4217 alphabetic code, e.g. ``USD``."""

Rate = Annotated[Decimal, Field(allow_inf_nan=False)]
"""A fraction: 0.08 means 8%."""

Amount = Annotated[Decimal, Field(allow_inf_nan=False)]
"""A monetary amount in the owning object's currency and scale."""


class DomainModel(BaseModel):
    """Immutable, strict base for all domain objects."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class Scale(StrEnum):
    """The unit multiplier that amounts are expressed in."""

    UNITS = "units"
    THOUSANDS = "thousands"
    MILLIONS = "millions"
    BILLIONS = "billions"

    @property
    def multiplier(self) -> Decimal:
        return {
            Scale.UNITS: Decimal(1),
            Scale.THOUSANDS: Decimal(10) ** 3,
            Scale.MILLIONS: Decimal(10) ** 6,
            Scale.BILLIONS: Decimal(10) ** 9,
        }[self]


def rescale(value: Decimal, from_scale: Scale, to_scale: Scale) -> Decimal:
    """Convert an amount between scales (e.g. thousands -> millions). Exact."""
    if from_scale == to_scale:
        return value
    return value * from_scale.multiplier / to_scale.multiplier


class ValueKind(StrEnum):
    """Provenance class of a number. Shown to users so they can tell facts from estimates."""

    REPORTED = "reported"  # as filed by the company / data provider
    CALCULATED = "calculated"  # derived deterministically from reported figures
    ASSUMPTION = "assumption"  # user- or analyst-supplied input
    FORECAST = "forecast"  # projected from assumptions
    AI_EXPLANATION = "ai_explanation"  # model-generated narrative, never a source of figures


class FiscalPeriod(StrEnum):
    FY = "FY"
    Q1 = "Q1"
    Q2 = "Q2"
    Q3 = "Q3"
    Q4 = "Q4"


class ReportingPeriod(DomainModel):
    fiscal_year: int = Field(ge=1900, le=2200)
    fiscal_period: FiscalPeriod = FiscalPeriod.FY
    period_start: date | None = None
    period_end: date

    @model_validator(mode="after")
    def _start_before_end(self) -> Self:
        if self.period_start is not None and self.period_start >= self.period_end:
            raise ValueError("period_start must be before period_end")
        return self

    @property
    def label(self) -> str:
        if self.fiscal_period == FiscalPeriod.FY:
            return f"FY{self.fiscal_year}"
        return f"{self.fiscal_period.value} FY{self.fiscal_year}"


class SourceRef(DomainModel):
    """Where a set of figures came from."""

    provider: str = Field(min_length=1, max_length=100)
    retrieved_at: datetime
    url: str | None = Field(default=None, max_length=2000)
    document_id: str | None = Field(default=None, max_length=200)
    page: int | None = Field(default=None, ge=1)


class IssueSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"


class Issue(DomainModel):
    """A non-fatal observation about inputs or results (fatal problems raise instead)."""

    code: str
    severity: IssueSeverity = IssueSeverity.WARNING
    message: str
