"""Company directory, ingestion of reported financials, and loading them into the domain."""

import logging
from datetime import UTC, datetime
from decimal import Decimal

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
from app.domain.types import ReportingPeriod, Scale, SourceRef, ValueKind
from app.models import Company, FinancialLineItem, FinancialPeriod
from app.providers.base import (
    CompanyListing,
    FinancialDataProvider,
    IngestionResult,
    ProviderError,
    ProviderNotFoundError,
)

logger = logging.getLogger("app.companies")

SEARCH_LIMIT_MAX = 50


def _like_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search(db: Session, query: str, limit: int = 20) -> list[Company]:
    q = query.strip().lower()
    if not q:
        return []
    pattern = f"%{_like_escape(q)}%"
    prefix = f"{_like_escape(q)}%"
    stmt = (
        select(Company)
        .where(
            or_(
                func.lower(Company.ticker).like(prefix, escape="\\"),
                func.lower(Company.name).like(pattern, escape="\\"),
            )
        )
        # exact ticker first, then ticker prefix matches, then by name
        .order_by((func.lower(Company.ticker) != q), func.length(Company.ticker), Company.name)
        .limit(min(limit, SEARCH_LIMIT_MAX))
    )
    return list(db.scalars(stmt))


def get_by_ticker(db: Session, ticker: str) -> Company:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if company is None:
        raise AppError("company_not_found", f"Company {ticker.upper()} not found", 404)
    return company


def _upsert_listing(db: Session, listing: CompanyListing) -> Company:
    company = db.scalar(
        select(Company).where(or_(Company.cik == listing.cik, Company.ticker == listing.ticker))
    )
    if company is None:
        company = Company(ticker=listing.ticker, cik=listing.cik, name=listing.name)
        db.add(company)
    else:
        company.ticker, company.cik, company.name = listing.ticker, listing.cik, listing.name
    company.exchange = listing.exchange
    return company


def sync_directory(db: Session, provider: FinancialDataProvider) -> int:
    """Upsert the provider's full company directory (used by the CLI)."""
    listings = provider.list_companies()
    existing = {c.cik: c for c in db.scalars(select(Company))}
    for listing in listings:
        company = existing.get(listing.cik)
        if company is None:
            db.add(
                Company(
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


def ingest(
    db: Session, provider: FinancialDataProvider, ticker: str
) -> tuple[Company, IngestionResult]:
    """Fetch annual financials from the provider and replace the stored periods."""
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
        logger.warning("provider_error", extra={"provider": provider.name, "error": str(exc)})
        raise AppError(
            "provider_unavailable", "The financial data provider is unavailable", 502
        ) from None

    company = _upsert_listing(db, listing)
    db.flush()
    existing = {
        (p.fiscal_year, p.fiscal_period): p
        for p in db.scalars(select(FinancialPeriod).where(FinancialPeriod.company_id == company.id))
    }
    for ingested in result.periods:
        period = existing.get((ingested.fiscal_year, ingested.fiscal_period))
        if period is None:
            period = FinancialPeriod(
                company_id=company.id,
                fiscal_year=ingested.fiscal_year,
                fiscal_period=ingested.fiscal_period,
            )
            db.add(period)
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
            "provider": result.provider,
            "periods": len(result.periods),
            "warnings": len(result.warnings),
        },
    )
    return company, result


def list_periods(db: Session, company: Company) -> list[FinancialPeriod]:
    stmt = (
        select(FinancialPeriod)
        .where(FinancialPeriod.company_id == company.id)
        .options(selectinload(FinancialPeriod.line_items))
        .order_by(FinancialPeriod.period_end.desc())
    )
    return list(db.scalars(stmt))


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
        income=IncomeStatement(**by_statement["income"]),
        balance=BalanceSheet(**by_statement["balance"]),
        cash_flow=CashFlowStatement(**by_statement["cash_flow"]),
    )


def ratios(db: Session, company: Company, fiscal_year: int | None) -> RatioReport:
    periods = [p for p in list_periods(db, company) if p.fiscal_period == "FY"]
    if not periods:
        raise AppError(
            "no_financial_data", f"No annual financial data stored for {company.ticker}", 404
        )
    by_year = {p.fiscal_year: p for p in periods}
    year = fiscal_year if fiscal_year is not None else max(by_year)
    current = by_year.get(year)
    if current is None:
        raise AppError("no_financial_data", f"No FY{year} data for {company.ticker}", 404)
    prior = by_year.get(year - 1)
    return compute_ratios(
        to_domain(company, current), to_domain(company, prior) if prior is not None else None
    )
