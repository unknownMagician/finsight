"""Companies, their exchange listings, and reported financial data (one row per line item,
with provenance).

Identity: a company belongs to one market (``IN`` or ``US``) and has a ``ticker`` that is unique
within that market only (``INFY`` is both an NSE symbol and a NYSE ADR). Indian companies are
identified by their equity ISIN when the source provides one, and each exchange listing (NSE,
BSE) is a separate ``Instrument``. US companies keep their SEC CIK.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

# Large enough for any reported amount at units scale (INR or USD), with 6 decimal places for EPS.
AMOUNT = Numeric(28, 6)


class Company(TimestampMixin, Base):
    __tablename__ = "companies"
    __table_args__ = (UniqueConstraint("market", "ticker"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    market: Mapped[str] = mapped_column(String(2), nullable=False)  # IN | US
    # Upper-case display symbol, unique per market. For IN: the NSE symbol when listed on NSE,
    # else the BSE symbol (else the ISIN if that symbol is already taken by another company).
    ticker: Mapped[str] = mapped_column(String(30), nullable=False)
    cik: Mapped[str | None] = mapped_column(String(10), unique=True)  # US only, zero-padded
    isin: Mapped[str | None] = mapped_column(String(12), unique=True)  # IN equity ISIN
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    exchange: Mapped[str | None] = mapped_column(String(50))  # US listing venue (SEC directory)
    last_ingested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    periods: Mapped[list["FinancialPeriod"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    instruments: Mapped[list["Instrument"]] = relationship(
        back_populates="company", cascade="all, delete-orphan", order_by="Instrument.exchange"
    )


class Instrument(TimestampMixin, Base):
    """One exchange-specific listing of a company (e.g. RELIANCE on NSE, RELIANCE on BSE)."""

    __tablename__ = "instruments"
    __table_args__ = (
        UniqueConstraint("exchange", "isin"),
        Index("ix_instruments_exchange_symbol", "exchange", "symbol"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    exchange: Mapped[str] = mapped_column(String(10), nullable=False)  # NSE | BSE
    symbol: Mapped[str] = mapped_column(String(30), nullable=False)
    isin: Mapped[str | None] = mapped_column(String(12))  # as supplied by the source
    series: Mapped[str | None] = mapped_column(String(10))
    name: Mapped[str] = mapped_column(String(255), nullable=False)  # exchange's short name
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    # active | not_in_latest_snapshot. A listing missing from the latest trading-day snapshot
    # did not trade that day; that is not proof of delisting, so it is not called "delisted".
    listing_status: Mapped[str] = mapped_column(String(30), nullable=False)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    provider_instrument_key: Mapped[str | None] = mapped_column(String(100))
    last_traded_on: Mapped[date | None] = mapped_column(Date)
    former_symbols: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    company: Mapped[Company] = relationship(back_populates="instruments")


class FinancialPeriod(TimestampMixin, Base):
    __tablename__ = "financial_periods"
    __table_args__ = (UniqueConstraint("company_id", "fiscal_year", "fiscal_period", "basis"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    fiscal_period: Mapped[str] = mapped_column(String(2), nullable=False)  # FY, Q1..Q4
    # consolidated | standalone | unspecified (source does not say). Never mixed in a series.
    basis: Mapped[str] = mapped_column(String(20), nullable=False, server_default="unspecified")
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
    # Provenance: the source concept (e.g. XBRL "us-gaap:Revenues" or "yfinance:Total Revenue")
    # and, for SEC data, the filing accession it came from.
    source_concept: Mapped[str | None] = mapped_column(String(255))
    source_accession: Mapped[str | None] = mapped_column(String(30))

    period: Mapped[FinancialPeriod] = relationship(back_populates="line_items")
