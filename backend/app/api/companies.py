from typing import Annotated

from fastapi import APIRouter, Path, Query

from app.api.deps import CurrentUser, DbSession, IngestRateLimit, Provider
from app.domain.ratios import RatioReport
from app.models import FinancialPeriod
from app.schemas import (
    CompanyOut,
    FinancialsOut,
    IngestOut,
    LineItemOut,
    PeriodOut,
    SourceOut,
)
from app.services import companies as company_service

router = APIRouter(prefix="/companies", tags=["companies"])

TickerPath = Annotated[str, Path(pattern=r"^[A-Za-z0-9.\-]{1,20}$")]


def _period_out(period: FinancialPeriod) -> PeriodOut:
    return PeriodOut(
        fiscal_year=period.fiscal_year,
        fiscal_period=period.fiscal_period,
        period_start=period.period_start,
        period_end=period.period_end,
        currency=period.currency,
        scale=period.scale,
        kind=period.kind,
        source=SourceOut(
            provider=period.source_provider,
            url=period.source_url,
            retrieved_at=period.retrieved_at,
        ),
        line_items=[
            LineItemOut.model_validate(i)
            for i in sorted(period.line_items, key=lambda i: (i.statement, i.item))
        ],
    )


@router.get("", response_model=list[CompanyOut])
def search_companies(
    _: CurrentUser,
    db: DbSession,
    q: Annotated[str, Query(min_length=1, max_length=100)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> list[CompanyOut]:
    return [CompanyOut.model_validate(c) for c in company_service.search(db, q, limit)]


@router.get("/{ticker}", response_model=CompanyOut)
def get_company(_: CurrentUser, db: DbSession, ticker: TickerPath) -> CompanyOut:
    return CompanyOut.model_validate(company_service.get_by_ticker(db, ticker))


@router.post("/{ticker}/ingest", response_model=IngestOut, dependencies=[IngestRateLimit])
def ingest_company(
    _: CurrentUser, db: DbSession, provider: Provider, ticker: TickerPath
) -> IngestOut:
    company, result = company_service.ingest(db, provider, ticker)
    return IngestOut(
        company=CompanyOut.model_validate(company),
        periods_ingested=len(result.periods),
        fiscal_years=[p.fiscal_year for p in result.periods],
        warnings=result.warnings,
    )


@router.get("/{ticker}/financials", response_model=FinancialsOut)
def get_financials(_: CurrentUser, db: DbSession, ticker: TickerPath) -> FinancialsOut:
    company = company_service.get_by_ticker(db, ticker)
    periods = company_service.list_periods(db, company)
    return FinancialsOut(
        company=CompanyOut.model_validate(company), periods=[_period_out(p) for p in periods]
    )


@router.get("/{ticker}/ratios", response_model=RatioReport)
def get_ratios(
    _: CurrentUser,
    db: DbSession,
    ticker: TickerPath,
    fiscal_year: Annotated[int | None, Query(ge=1900, le=2200)] = None,
) -> RatioReport:
    company = company_service.get_by_ticker(db, ticker)
    return company_service.ratios(db, company, fiscal_year)
