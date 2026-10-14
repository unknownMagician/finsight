"""Companies and their reported financial data (one row per line item, with provenance)."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

# Large enough for any reported USD amount at units scale, with 6 decimal places for EPS.
AMOUNT = Numeric(28, 6)


class Company(TimestampMixin, Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)  # upper-case
    cik: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)  # zero-padded
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    exchange: Mapped[str | None] = mapped_column(String(50))
    last_ingested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    periods: Mapped[list["FinancialPeriod"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )


class FinancialPeriod(TimestampMixin, Base):
    __tablename__ = "financial_periods"
    __table_args__ = (UniqueConstraint("company_id", "fiscal_year", "fiscal_period"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    fiscal_period: Mapped[str] = mapped_column(String(2), nullable=False)  # FY, Q1..Q4
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    scale: Mapped[str] = mapped_column(String(10), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # ValueKind
    source_provider: Mapped[str] = mapped_column(String(100), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(2000))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    company: Mapped[Company] = relationship(back_populates="periods")
    line_items: Mapped[list["FinancialLineItem"]] = relationship(
        back_populates="period", cascade="all, delete-orphan"
    )


class FinancialLineItem(Base):
    __tablename__ = "financial_line_items"
    __table_args__ = (UniqueConstraint("period_id", "statement", "item"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    period_id: Mapped[int] = mapped_column(
        ForeignKey("financial_periods.id", ondelete="CASCADE"), nullable=False, index=True
    )
    statement: Mapped[str] = mapped_column(String(20), nullable=False)  # income|balance|cash_flow
    item: Mapped[str] = mapped_column(String(64), nullable=False)  # domain field name
    value: Mapped[Decimal] = mapped_column(AMOUNT, nullable=False)
    # Provenance: the source concept (e.g. XBRL "us-gaap:Revenues") and filing it came from.
    source_concept: Mapped[str | None] = mapped_column(String(255))
    source_accession: Mapped[str | None] = mapped_column(String(30))

    period: Mapped[FinancialPeriod] = relationship(back_populates="line_items")
