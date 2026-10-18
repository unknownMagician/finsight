"""Company lookup/search, ingestion of reported financials, and loading them into the domain.

Markets:
- ``IN`` (default): companies come from the market-data provider's instrument directory (see
  ``services.instruments``) and statements from the configured ``FundamentalsProvider``.
- ``US`` (optional): companies and annual statements come from SEC EDGAR.
"""

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import AppError
from app.domain.ratios import RatioReport, compute_ratios
from app.domain.statements import (
    BalanceSheet,
    CashFlowStatement,
    FinancialPeriodData,
    IncomeStatement,
)
from app.domain.types import ReportingBasis, ReportingPeriod, Scale, SourceRef, ValueKind
from app.models import Company, FinancialLineItem, FinancialPeriod, Instrument
from app.providers.base import (
    CompanyListing,
    FinancialDataProvider,
    FundamentalsProvider,
    IngestionResult,
    InstrumentRef,
    ProviderError,
    ProviderNotFoundError,
    ProviderRateLimitedError,
)

logger = logging.getLogger("app.companies")

Market = Literal["IN", "US"]
PeriodType = Literal["annual", "quarterly"]
SEARCH_LIMIT_MAX = 50
# When the caller does not choose, consolidated figures are preferred (they include
# subsidiaries); the chosen basis is always reported back.
BASIS_PREFERENCE: tuple[ReportingBasis, ...] = ("consolidated", "standalone", "unspecified")


def _like_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search(
    db: Session,
    query: str,
    limit: int = 20,
    *,
    market: Market = "US",
    exchange: str | None = None,
) -> list[Company]:
    q = query.strip().lower()
    if not q:
        return []
    pattern = f"%{_like_escape(q)}%"
    prefix = f"{_like_escape(q)}%"
    matches = [
        func.lower(Company.ticker).like(prefix, escape="\\"),
        func.lower(Company.name).like(pattern, escape="\\"),
    ]
    if market == "IN":
        listing_match = select(Instrument.company_id).where(
            or_(
                func.lower(Instrument.symbol).like(prefix, escape="\\"),
                func.lower(Instrument.name).like(pattern, escape="\\"),
                Instrument.isin == q.upper(),
            )
        )
        matches.append(Company.id.in_(listing_match))
    stmt = select(Company).where(Company.market == market, or_(*matches))
    if exchange is not None:
        stmt = stmt.where(
            Company.id.in_(
                select(Instrument.company_id).where(
                    Instrument.exchange == exchange, Instrument.listing_status == "active"
                )
            )
        )
    stmt = (
        stmt.options(selectinload(Company.instruments))
        # exact ticker first, then ticker prefix matches, then by name
        .order_by((func.lower(Company.ticker) != q), func.length(Company.ticker), Company.name)
        .limit(min(limit, SEARCH_LIMIT_MAX))
    )
    return list(db.scalars(stmt))


def get_company(db: Session, ref: str, market: Market) -> Company:
    """By ticker within the market; Indian companies can also be addressed by ISIN."""
    key = ref.strip().upper()
    stmt = (
        select(Company).where(Company.market == market).options(selectinload(Company.instruments))
    )
    company = db.scalar(stmt.where(Company.ticker == key))
    if company is None and market == "IN":
        company = db.scalar(stmt.where(Company.isin == key))
    if company is None:
        raise AppError("company_not_found", f"Company {key} not found in market {market}", 404)
    return company


def get_by_ticker(db: Session, ticker: str, market: Market = "US") -> Company:
    return get_company(db, ticker, market)


# --- ingestion ----------------------------------------------------------------------------------


def _upsert_listing(db: Session, listing: CompanyListing) -> Company:
    company = db.scalar(
        select(Company).where(
            Company.market == "US",
            or_(Company.cik == listing.cik, Company.ticker == listing.ticker),
        )
    )
    if company is None:
        company = Company(market="US", ticker=listing.ticker, cik=listing.cik, name=listing.name)
        db.add(company)
    else:
        company.ticker, company.cik, company.name = listing.ticker, listing.cik, listing.name
    company.exchange = listing.exchange
    return company


def sync_directory(db: Session, provider: FinancialDataProvider) -> int:
    """Upsert the SEC company directory (US market; used by the CLI)."""
    listings = provider.list_companies()
    existing = {c.cik: c for c in db.scalars(select(Company).where(Company.market == "US"))}
    for listing in listings:
        company = existing.get(listing.cik)
        if company is None:
            db.add(
                Company(
                    market="US",
                    ticker=listing.ticker,
                    cik=listing.cik,
                    name=listing.name,
                    exchange=listing.exchange,
                )
            )
        else:
            company.name, company.exchange = listing.name, listing.exchange
    db.commit()
    return len(listings)


def _provider_failure(provider_name: str, exc: ProviderError) -> AppError:
    logger.warning("provider_error", extra={"provider": provider_name, "error": str(exc)})
    if isinstance(exc, ProviderRateLimitedError):
        return AppError(
            "provider_rate_limited", "The data provider's free-tier limit was reached", 503
        )
    return AppError("provider_unavailable", "The financial data provider is unavailable", 502)


def _store_result(db: Session, company: Company, result: IngestionResult) -> None:
    """Replace stored periods that the result covers (matched on year, period and basis)."""
    existing = {
        (p.fiscal_year, p.fiscal_period, p.basis): p
        for p in db.scalars(select(FinancialPeriod).where(FinancialPeriod.company_id == company.id))
    }
    for ingested in result.periods:
        key = (ingested.fiscal_year, ingested.fiscal_period, ingested.basis)
        period = existing.get(key)
        if period is None:
            period = FinancialPeriod(
                company_id=company.id,
                fiscal_year=ingested.fiscal_year,
                fiscal_period=ingested.fiscal_period,
                basis=ingested.basis,
            )
            db.add(period)
            existing[key] = period
        else:
            period.line_items.clear()
            db.flush()  # delete old items before inserting replacements (unique constraint)
        period.period_start = ingested.period_start
        period.period_end = ingested.period_end
        period.currency = ingested.currency
        period.scale = ingested.scale
        period.kind = ValueKind.REPORTED.value
        period.source_provider = result.provider
        period.source_url = result.source_url
        period.retrieved_at = result.retrieved_at
        period.line_items.extend(
            FinancialLineItem(
                statement=i.statement,
                item=i.item,
                value=i.value,
                source_concept=i.source_concept,
                source_accession=i.source_accession,
            )
            for i in ingested.items
        )
    company.last_ingested_at = datetime.now(UTC)
    db.commit()
    db.refresh(company)
    logger.info(
        "ingested_financials",
        extra={
            "ticker": company.ticker,
            "market": company.market,
            "provider": result.provider,
            "periods": len(result.periods),
            "warnings": len(result.warnings),
        },
    )


def ingest(
    db: Session, provider: FinancialDataProvider, ticker: str
) -> tuple[Company, IngestionResult]:
    """US: fetch annual financials from SEC EDGAR and replace the stored periods."""
    try:
        listing = provider.lookup(ticker)
        if listing is None:
            raise AppError(
                "company_not_found", f"{ticker.upper()} not found at {provider.name}", 404
            )
        result = provider.fetch_annual_financials(listing)
    except ProviderNotFoundError:
        raise AppError(
            "company_not_found", f"{provider.name} has no financial data for {ticker.upper()}", 404
        ) from None
    except ProviderError as exc:
        raise _provider_failure(provider.name, exc) from None

    company = _upsert_listing(db, listing)
    db.flush()
    _store_result(db, company, result)
    return company, result


def preferred_instrument(company: Company) -> Instrument:
    """The listing used to fetch company-level data: active NSE, else active BSE, else any."""
    ranked = sorted(
        company.instruments,
        key=lambda i: (i.listing_status != "active", i.exchange != "NSE", i.symbol),
    )
    if not ranked:
        raise AppError("listing_not_found", f"{company.ticker} has no exchange listings", 404)
    return ranked[0]


def ingest_india(db: Session, provider: FundamentalsProvider, company: Company) -> IngestionResult:
    """IN: fetch annual + quarterly statements for the company's preferred listing."""
    instrument = preferred_instrument(company)
    ref = InstrumentRef(
        exchange=instrument.exchange,  # type: ignore[arg-type]
        symbol=instrument.symbol,
        isin=instrument.isin,
        name=company.name,
    )
    try:
        result = provider.fetch_financials(ref)
    except ProviderNotFoundError:
        raise AppError(
            "no_financial_data",
            f"{provider.name} has no financial statements for {instrument.exchange}:"
            f"{instrument.symbol}",
            404,
        ) from None
    except ProviderError as exc:
        raise _provider_failure(provider.name, exc) from None
    _store_result(db, company, result)
    return result


# --- reading stored financials ------------------------------------------------------------------


def list_periods(
    db: Session,
    company: Company,
    *,
    period_type: PeriodType | None = None,
    basis: ReportingBasis | None = None,
) -> list[FinancialPeriod]:
    stmt = (
        select(FinancialPeriod)
        .where(FinancialPeriod.company_id == company.id)
        .options(selectinload(FinancialPeriod.line_items))
        .order_by(FinancialPeriod.period_end.desc(), FinancialPeriod.basis)
    )
    if period_type == "annual":
        stmt = stmt.where(FinancialPeriod.fiscal_period == "FY")
    elif period_type == "quarterly":
        stmt = stmt.where(FinancialPeriod.fiscal_period != "FY")
    if basis is not None:
        stmt = stmt.where(FinancialPeriod.basis == basis)
    return list(db.scalars(stmt))


def available_bases(db: Session, company: Company) -> list[ReportingBasis]:
    rows = set(
        db.scalars(
            select(FinancialPeriod.basis).where(FinancialPeriod.company_id == company.id).distinct()
        )
    )
    return [b for b in BASIS_PREFERENCE if b in rows]


def choose_basis(db: Session, company: Company, requested: ReportingBasis | None) -> ReportingBasis:
    bases = available_bases(db, company)
    if not bases:
        raise AppError("no_financial_data", f"No financial data stored for {company.ticker}", 404)
    if requested is None:
        return bases[0]
    if requested not in bases:
        raise AppError(
            "no_financial_data",
            f"No {requested} statements stored for {company.ticker}; available: "
            + ", ".join(bases),
            404,
        )
    return requested


def to_domain(company: Company, period: FinancialPeriod) -> FinancialPeriodData:
    by_statement: dict[str, dict[str, Decimal]] = {"income": {}, "balance": {}, "cash_flow": {}}
    for item in period.line_items:
        by_statement.setdefault(item.statement, {})[item.item] = Decimal(item.value)
    return FinancialPeriodData(
        company=company.ticker,
        period=ReportingPeriod(
            fiscal_year=period.fiscal_year,
            fiscal_period=period.fiscal_period,
            period_start=period.period_start,
            period_end=period.period_end,
        ),
        currency=period.currency,
        scale=Scale(period.scale),
        source=SourceRef(
            provider=period.source_provider,
            retrieved_at=period.retrieved_at,
            url=period.source_url,
        ),
        kind=ValueKind(period.kind),
        basis=period.basis,
        income=IncomeStatement(**by_statement["income"]),
        balance=BalanceSheet(**by_statement["balance"]),
        cash_flow=CashFlowStatement(**by_statement["cash_flow"]),
    )


def annual_periods(
    db: Session, company: Company, basis: ReportingBasis
) -> dict[int, FinancialPeriod]:
    return {p.fiscal_year: p for p in list_periods(db, company, period_type="annual", basis=basis)}


def ratios(
    db: Session,
    company: Company,
    fiscal_year: int | None,
    basis: ReportingBasis | None = None,
) -> RatioReport:
    """Annual ratios; the prior year (for growth/averages) is taken from the same basis only."""
    chosen = choose_basis(db, company, basis)
    by_year = annual_periods(db, company, chosen)
    if not by_year:
        raise AppError(
            "no_financial_data",
            f"No annual {chosen} financial data stored for {company.ticker}",
            404,
        )
    year = fiscal_year if fiscal_year is not None else max(by_year)
    current = by_year.get(year)
    if current is None:
        raise AppError("no_financial_data", f"No FY{year} data for {company.ticker}", 404)
    prior = by_year.get(year - 1)
    return compute_ratios(
        to_domain(company, current), to_domain(company, prior) if prior is not None else None
    )
