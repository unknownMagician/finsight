"""Report content: sections of labelled figures/tables. Stored as JSON (Decimals as strings)."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

# reported | calculated | assumption | forecast | extracted | market | ai_explanation
Provenance = Literal[
    "reported", "calculated", "assumption", "forecast", "extracted", "market", "ai_explanation"
]


class ReportFigure(BaseModel):
    label: str
    value: Decimal | None
    display: str  # formatted for people (Indian grouping, ₹ crore, %)
    kind: Provenance
    period: str | None = None
    basis: str | None = None
    source: str | None = None
    note: str | None = None


class ReportTable(BaseModel):
    caption: str
    kind: Provenance
    columns: list[str]
    rows: list[list[str]]
    source: str | None = None


class ReportSection(BaseModel):
    key: str
    title: str
    status: Literal["ok", "unavailable"] = "ok"
    reason: str | None = None
    figures: list[ReportFigure] = Field(default_factory=list)
    tables: list[ReportTable] = Field(default_factory=list)
    paragraphs: list[str] = Field(default_factory=list)


class ReportCompany(BaseModel):
    market: str
    ticker: str
    name: str
    isin: str | None
    listings: list[str]  # "NSE: RELIANCE"


class ReportContent(BaseModel):
    title: str
    generated_at: datetime
    company: ReportCompany
    exchange: str | None
    basis: str | None
    sections: list[ReportSection]
    disclaimers: list[str]
    engine_version: str
