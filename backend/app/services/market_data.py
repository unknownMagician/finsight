"""Prices, corporate actions and market multiples for Indian listings.

All provider calls go through the TTL cache, so repeated requests for the same data do not
reach free-tier providers. Every result carries its provider, data nature (end-of-day / demo),
the trading date it describes, when it was retrieved, and whether it came from cache.
Nothing is labelled real-time: the integrated free sources are end-of-day only.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.cache import TTLCache
from app.core.errors import AppError
from app.domain.market_multiples import MarketMultiplesReport, MarketPrice, compute_market_multiples
from app.domain.types import Issue, ReportingBasis
from app.models import Company, FinancialPeriod, Instrument
from app.providers.base import (
    Capability,
    CapabilityUnavailableError,
    CorporateAction,
    Exchange,
    MarketDataProvider,
    PriceBar,
    PriceSeries,
    ProviderError,
    ProviderNotFoundError,
    ProviderRateLimitedError,
    ProviderStatus,
)
from app.services import companies as company_service
from app.services.instruments import resolve_listing

IST = timezone(timedelta(hours=5, minutes=30))  # India has no DST
MAX_HISTORY_DAYS = 366 * 20
QUOTE_LOOKBACK_DAYS = 21
SHARE_COUNT_EVENTS = frozenset({"split", "bonus", "rights", "merger"})


def today_ist() -> date:
    return datetime.now(IST).date()


def _map_provider_error(exc: ProviderError, what: str) -> AppError:
    if isinstance(exc, CapabilityUnavailableError):
        return AppError(
            "capability_unavailable", f"The configured provider does not offer {what}", 501
        )
    if isinstance(exc, ProviderNotFoundError):
        return AppError("market_data_not_found", f"No {what} available for this listing", 404)
    if isinstance(exc, ProviderRateLimitedError):
        return AppError(
            "provider_rate_limited",
            "The market-data provider's free-tier limit was reached; try again shortly",
            503,
        )
    return AppError("provider_unavailable", "The market-data provider is unavailable", 502)


def _require(provider: MarketDataProvider, capability: Capability, what: str) -> None:
    if capability not in provider.capabilities:
        raise AppError(
            "capability_unavailable",
            f"The configured provider ({provider.name}) does not offer {what}",
            501,
        )


@dataclass(frozen=True)
class SeriesResult:
    series: PriceSeries
    cached: bool
    stale: bool
    as_of: date | None


def price_history(
    provider: MarketDataProvider,
    cache: TTLCache,
    instrument: Instrument,
    start: date,
    end: date,
    *,
    stale_after_days: int,
    today: date | None = None,
) -> SeriesResult:
    _require(provider, Capability.EOD_PRICES, "end-of-day prices")
    if start > end:
        raise AppError("invalid_range", "start must be on or before end", 422)
    if (end - start).days > MAX_HISTORY_DAYS:
        raise AppError("invalid_range", "at most 20 years of history per request", 422)
    exchange: Exchange = instrument.exchange  # type: ignore[assignment]
    key = ("bars", provider.name, exchange, instrument.symbol, start, end)
    try:
        series, cached = cache.get_or_load(
            key, lambda: provider.fetch_eod_bars(exchange, instrument.symbol, start, end)
        )
    except ProviderError as exc:
        raise _map_provider_error(exc, "prices") from None
    as_of = series.bars[-1].date if series.bars else None
    current = today or today_ist()
    stale = as_of is None or (current - as_of).days > stale_after_days
    return SeriesResult(series, cached, stale, as_of)


@dataclass(frozen=True)
class QuoteResult:
    instrument: Instrument
    series: PriceSeries
    bar: PriceBar
    change: Decimal | None
    change_pct: Decimal | None
    cached: bool
    stale: bool


def latest_quote(
    provider: MarketDataProvider,
    cache: TTLCache,
    instrument: Instrument,
    *,
    stale_after_days: int,
    today: date | None = None,
) -> QuoteResult:
    """The most recent end-of-day bar (not a live quote)."""
    current = today or today_ist()
    result = price_history(
        provider,
        cache,
        instrument,
        current - timedelta(days=QUOTE_LOOKBACK_DAYS),
        current,
        stale_after_days=stale_after_days,
        today=current,
    )
    if not result.series.bars:
        raise AppError(
            "market_data_not_found",
            f"No trades for {instrument.exchange}:{instrument.symbol} in the last "
            f"{QUOTE_LOOKBACK_DAYS} days",
            404,
        )
    bar = result.series.bars[-1]
    change = change_pct = None
    if bar.prev_close is not None and bar.prev_close > 0:
        change = bar.close - bar.prev_close
        change_pct = change / bar.prev_close
    return QuoteResult(
        instrument, result.series, bar, change, change_pct, result.cached, result.stale
    )


@dataclass(frozen=True)
class ActionsResult:
    provider: str
    actions: list[CorporateAction]
    retrieved_at: datetime
    source_urls: list[str]
    cached: bool


def corporate_actions(
    provider: MarketDataProvider, cache: TTLCache, company: Company
) -> ActionsResult:
    """Actions for the company's listings, matched by ISIN (or exact exchange+symbol)."""
    _require(provider, Capability.CORPORATE_ACTIONS, "corporate actions")
    listings = {(i.exchange, i.symbol) for i in company.instruments}
    actions: dict[tuple[object, ...], CorporateAction] = {}
    urls: list[str] = []
    all_cached = True
    retrieved: list[datetime] = []
    for symbol in sorted({symbol for _, symbol in listings}):
        try:
            result, cached = cache.get_or_load(
                ("actions", provider.name, symbol),
                lambda symbol=symbol: provider.fetch_corporate_actions(symbol),  # type: ignore[misc]
            )
        except ProviderError as exc:
            raise _map_provider_error(exc, "corporate actions") from None
        all_cached = all_cached and cached
        retrieved.append(result.retrieved_at)
        if result.source_url:
            urls.append(result.source_url)
        for action in result.actions:
            belongs = (
                action.isin == company.isin
                if company.isin and action.isin
                else (action.exchange, action.symbol) in listings
            )
            if belongs:
                key = (action.exchange, action.ex_date, action.action_type, action.description)
                actions[key] = action
    ordered = sorted(actions.values(), key=lambda a: (a.ex_date, a.exchange), reverse=True)
    return ActionsResult(provider.name, ordered, min(retrieved), urls, all_cached)


@dataclass(frozen=True)
class ValuationSnapshot:
    report: MarketMultiplesReport
    quote: QuoteResult
    period: FinancialPeriod
    basis: ReportingBasis


def _trailing_dividends(
    actions: list[CorporateAction], exchange: str, price_date: date
) -> tuple[Decimal | None, str]:
    window_start = price_date - timedelta(days=365)
    dividends = [
        a
        for a in actions
        if a.exchange == exchange
        and a.action_type == "dividend"
        and window_start < a.ex_date <= price_date
    ]
    if any(a.cash_amount is None for a in dividends):
        return None, "a dividend in the trailing year has no stated amount"
    total = sum((a.cash_amount for a in dividends if a.cash_amount is not None), Decimal(0))
    return total, (
        f"sum of {len(dividends)} {exchange} dividend(s) with ex-date in "
        f"({window_start}, {price_date}]"
    )


def valuation_snapshot(
    db: Session,
    provider: MarketDataProvider,
    cache: TTLCache,
    company: Company,
    *,
    exchange: str | None,
    basis: ReportingBasis | None,
    stale_after_days: int,
    today: date | None = None,
) -> ValuationSnapshot:
    instrument = resolve_listing(company, exchange)
    chosen = company_service.choose_basis(db, company, basis)
    annual = company_service.annual_periods(db, company, chosen)
    if not annual:
        raise AppError(
            "no_financial_data", f"No annual {chosen} statements stored for {company.ticker}", 404
        )
    period = annual[max(annual)]
    quote = latest_quote(
        provider, cache, instrument, stale_after_days=stale_after_days, today=today
    )
    price = MarketPrice(
        price=quote.bar.close,
        price_date=quote.bar.date,
        currency=quote.series.currency,
        source=f"{quote.series.provider} {quote.series.nature} close",
    )

    extra_issues: list[Issue] = []
    events: list[str] | None = None
    dividends: Decimal | None = None
    dividends_note: str | None = None
    try:
        actions = corporate_actions(provider, cache, company).actions
    except AppError:
        extra_issues.append(
            Issue(
                code="corporate_actions_unavailable",
                message="Corporate actions unavailable: share-count changes since the period "
                "end could not be checked and dividend yield is not computed.",
            )
        )
    else:
        events = [
            f"{a.action_type} ex {a.ex_date} ({a.description})"
            for a in actions
            if a.exchange == instrument.exchange
            and a.action_type in SHARE_COUNT_EVENTS
            and period.period_end < a.ex_date <= quote.bar.date
        ]
        dividends, dividends_note = _trailing_dividends(
            actions, instrument.exchange, quote.bar.date
        )

    try:
        report = compute_market_multiples(
            company_service.to_domain(company, period),
            price,
            share_count_events_after_period=events,
            trailing_dividends_per_share=dividends,
            dividends_note=dividends_note,
        )
    except ValueError as exc:
        raise AppError("invalid_valuation_inputs", str(exc), 422) from None
    if extra_issues:
        report = report.model_copy(update={"issues": [*report.issues, *extra_issues]})
    return ValuationSnapshot(report, quote, period, chosen)


def provider_status(provider: MarketDataProvider, cache: TTLCache) -> tuple[ProviderStatus, bool]:
    return cache.get_or_load(("status", provider.name), provider.status)
