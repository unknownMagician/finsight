"""Company routes. ``?market=IN|US`` selects the market (default ``FINSIGHT_DEFAULT_MARKET``,
``IN``). Indian companies are addressed by their ticker (NSE symbol, else BSE symbol) or ISIN;
market-data endpoints take ``?exchange=NSE|BSE`` and refuse to guess when it is ambiguous."""

from datetime import date, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Path, Query, Request

from app.api.deps import (
    CurrentUser,
    DbSession,
    IngestRateLimit,
    MarketCache,
    MarketDataRateLimit,
    MarketProvider,
    Today,
    get_fundamentals_provider,
    get_market_provider,
    get_provider,
    resolve_market,
)
from app.core.config import get_settings
from app.core.errors import AppError
from app.domain.ratios import RatioReport
from app.domain.types import ReportingBasis
from app.models import Company, FinancialPeriod, Instrument
from app.providers.base import PriceSeries
from app.schemas import (
    TICKER_PATTERN,
    CompanyOut,
    CorporateActionOut,
    CorporateActionsOut,
    FinancialsOut,
    FreshnessOut,
    IngestOut,
    InstrumentOut,
    LineItemOut,
    Market,
    PeriodOut,
    PriceBarOut,
    PriceHistoryOut,
    QuoteOut,
    SourceOut,
    ValuationSnapshotOut,
)
from app.services import companies as company_service
from app.services import instruments as instrument_service
from app.services import market_data
from app.services.market_data import QuoteResult

router = APIRouter(prefix="/companies", tags=["companies"])

TickerPath = Annotated[str, Path(pattern=TICKER_PATTERN)]
MarketQuery = Annotated[Market | None, Query()]
ExchangeQuery = Annotated[Literal["NSE", "BSE"] | None, Query()]
BasisQuery = Annotated[ReportingBasis | None, Query()]


def _period_out(period: FinancialPeriod) -> PeriodOut:
    return PeriodOut(
        fiscal_year=period.fiscal_year,
        fiscal_period=period.fiscal_period,
        basis=period.basis,
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


def _company(db: DbSession, ref: str, market: Market | None) -> Company:
    return company_service.get_company(db, ref, resolve_market(market))


def _indian(db: DbSession, ref: str) -> Company:
    return company_service.get_company(db, ref, "IN")


def _freshness(series: PriceSeries, *, cached: bool, stale: bool) -> FreshnessOut:
    return FreshnessOut(
        provider=series.provider,
        nature=series.nature,
        as_of=series.bars[-1].date if series.bars else None,
        retrieved_at=series.retrieved_at,
        cached=cached,
        stale=stale,
        adjusted=series.adjusted,
        source_url=series.source_url,
    )


def _quote_out(company: Company, quote: QuoteResult) -> QuoteOut:
    bar = quote.bar
    return QuoteOut(
        ticker=company.ticker,
        listing=InstrumentOut.model_validate(quote.instrument),
        currency=quote.series.currency,
        trade_date=bar.date,
        open=bar.open,
        high=bar.high,
        low=bar.low,
        close=bar.close,
        prev_close=bar.prev_close,
        change=quote.change,
        change_pct=quote.change_pct,
        volume=bar.volume,
        freshness=_freshness(quote.series, cached=quote.cached, stale=quote.stale),
    )


@router.get("", response_model=list[CompanyOut])
def search_companies(
    _: CurrentUser,
    db: DbSession,
    request: Request,
    q: Annotated[str, Query(min_length=1, max_length=100)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    market: MarketQuery = None,
    exchange: ExchangeQuery = None,
) -> list[CompanyOut]:
    chosen = resolve_market(market)
    if chosen == "IN":
        instrument_service.ensure_directory(db, get_market_provider(request))
    elif exchange is not None:
        raise AppError("invalid_request", "exchange filter applies to market IN only", 422)
    return [
        CompanyOut.model_validate(c)
        for c in company_service.search(db, q, limit, market=chosen, exchange=exchange)
    ]


@router.get("/{ticker}", response_model=CompanyOut)
def get_company(
    _: CurrentUser, db: DbSession, ticker: TickerPath, market: MarketQuery = None
) -> CompanyOut:
    return CompanyOut.model_validate(_company(db, ticker, market))


@router.post("/{ticker}/ingest", response_model=IngestOut, dependencies=[IngestRateLimit])
def ingest_company(
    _: CurrentUser,
    db: DbSession,
    request: Request,
    ticker: TickerPath,
    market: MarketQuery = None,
) -> IngestOut:
    """Fetch and store statements: SEC EDGAR for US, the fundamentals provider for IN."""
    if resolve_market(market) == "US":
        company, result = company_service.ingest(db, get_provider(request), ticker)
    else:
        company = _indian(db, ticker)
        result = company_service.ingest_india(db, get_fundamentals_provider(request), company)
    return IngestOut(
        company=CompanyOut.model_validate(company),
        provider=result.provider,
        periods_ingested=len(result.periods),
        fiscal_years=sorted({p.fiscal_year for p in result.periods}, reverse=True),
        warnings=result.warnings,
    )


@router.get("/{ticker}/financials", response_model=FinancialsOut)
def get_financials(
    _: CurrentUser,
    db: DbSession,
    ticker: TickerPath,
    market: MarketQuery = None,
    period_type: Annotated[Literal["annual", "quarterly"] | None, Query()] = None,
    basis: BasisQuery = None,
) -> FinancialsOut:
    company = _company(db, ticker, market)
    periods = company_service.list_periods(db, company, period_type=period_type, basis=basis)
    return FinancialsOut(
        company=CompanyOut.model_validate(company),
        available_bases=company_service.available_bases(db, company),
        periods=[_period_out(p) for p in periods],
    )


@router.get("/{ticker}/ratios", response_model=RatioReport)
def get_ratios(
    _: CurrentUser,
    db: DbSession,
    ticker: TickerPath,
    fiscal_year: Annotated[int | None, Query(ge=1900, le=2200)] = None,
    market: MarketQuery = None,
    basis: BasisQuery = None,
) -> RatioReport:
    company = _company(db, ticker, market)
    return company_service.ratios(db, company, fiscal_year, basis)


# --- Indian market data (end-of-day) -------------------------------------------------------------


def _listing(company: Company, exchange: str | None) -> Instrument:
    return instrument_service.resolve_listing(company, exchange)


@router.get("/{ticker}/quote", response_model=QuoteOut, dependencies=[MarketDataRateLimit])
def get_quote(
    _: CurrentUser,
    db: DbSession,
    provider: MarketProvider,
    cache: MarketCache,
    today: Today,
    ticker: TickerPath,
    exchange: ExchangeQuery = None,
) -> QuoteOut:
    """Latest available end-of-day bar for one listing (not real-time)."""
    company = _indian(db, ticker)
    quote = market_data.latest_quote(
        provider,
        cache,
        _listing(company, exchange),
        stale_after_days=get_settings().market_data_stale_after_days,
        today=today,
    )
    return _quote_out(company, quote)


@router.get("/{ticker}/prices", response_model=PriceHistoryOut, dependencies=[MarketDataRateLimit])
def get_prices(
    _: CurrentUser,
    db: DbSession,
    provider: MarketProvider,
    cache: MarketCache,
    today: Today,
    ticker: TickerPath,
    exchange: ExchangeQuery = None,
    start: date | None = None,
    end: date | None = None,
) -> PriceHistoryOut:
    """Daily end-of-day OHLCV (raw, unadjusted). Defaults to the last 365 days."""
    company = _indian(db, ticker)
    instrument = _listing(company, exchange)
    end_date = end or today
    start_date = start or end_date - timedelta(days=365)
    result = market_data.price_history(
        provider,
        cache,
        instrument,
        start_date,
        end_date,
        stale_after_days=get_settings().market_data_stale_after_days,
        today=today,
    )
    return PriceHistoryOut(
        ticker=company.ticker,
        listing=InstrumentOut.model_validate(instrument),
        currency=result.series.currency,
        bars=[PriceBarOut.model_validate(b, from_attributes=True) for b in result.series.bars],
        freshness=_freshness(result.series, cached=result.cached, stale=result.stale),
        warnings=result.series.warnings,
    )


@router.get(
    "/{ticker}/corporate-actions",
    response_model=CorporateActionsOut,
    dependencies=[MarketDataRateLimit],
)
def get_corporate_actions(
    _: CurrentUser,
    db: DbSession,
    provider: MarketProvider,
    cache: MarketCache,
    ticker: TickerPath,
) -> CorporateActionsOut:
    company = _indian(db, ticker)
    if not company.instruments:
        raise AppError("listing_not_found", f"{company.ticker} has no exchange listings", 404)
    result = market_data.corporate_actions(provider, cache, company)
    return CorporateActionsOut(
        ticker=company.ticker,
        provider=result.provider,
        retrieved_at=result.retrieved_at,
        cached=result.cached,
        source_urls=result.source_urls,
        actions=[
            CorporateActionOut.model_validate(a, from_attributes=True) for a in result.actions
        ],
    )


@router.get(
    "/{ticker}/valuation-snapshot",
    response_model=ValuationSnapshotOut,
    dependencies=[MarketDataRateLimit],
)
def get_valuation_snapshot(
    _: CurrentUser,
    db: DbSession,
    provider: MarketProvider,
    cache: MarketCache,
    today: Today,
    ticker: TickerPath,
    exchange: ExchangeQuery = None,
    basis: BasisQuery = None,
) -> ValuationSnapshotOut:
    """Market cap, EV, P/E, P/B, EV/EBITDA, dividend yield from the latest EOD close and the
    latest stored annual statements of one basis."""
    company = _indian(db, ticker)
    snap = market_data.valuation_snapshot(
        db,
        provider,
        cache,
        company,
        exchange=exchange,
        basis=basis,
        stale_after_days=get_settings().market_data_stale_after_days,
        today=today,
    )
    return ValuationSnapshotOut(
        ticker=company.ticker,
        listing=InstrumentOut.model_validate(snap.quote.instrument),
        basis=snap.basis,
        period_source=SourceOut(
            provider=snap.period.source_provider,
            url=snap.period.source_url,
            retrieved_at=snap.period.retrieved_at,
        ),
        quote=_quote_out(company, snap.quote),
        report=snap.report,
    )
