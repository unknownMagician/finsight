"""Indian instrument directory: sync from the market-data provider and listing resolution.

Identity rules:
- Listings are exchange-specific (an NSE and a BSE listing are two ``Instrument`` rows).
- Listings are grouped into one company by the provider's ``company_key``: the ISIN when the
  source supplies one (Tej: from the exchange bhavcopy), else a provider-scoped key.
- A symbol is never assumed unique across exchanges; lookups are always (exchange, symbol).
- A symbol change under the same ISIN is a rename: the old symbol is kept in
  ``former_symbols``. Listings absent from the latest snapshot are marked
  ``not_in_latest_snapshot`` (they did not trade that day), never "delisted".
"""

import logging
import threading
from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import AppError
from app.models import Company, Instrument
from app.providers.base import InstrumentListing, MarketDataProvider, ProviderError

logger = logging.getLogger("app.instruments")

_sync_lock = threading.Lock()


@dataclass(frozen=True)
class SyncReport:
    provider: str
    as_of: date
    listings: int
    companies_created: int
    instruments_created: int
    renamed: int
    marked_not_in_snapshot: int


def _canonical_symbol(listings: list[InstrumentListing]) -> str:
    nse = [listing for listing in listings if listing.exchange == "NSE"]
    return (nse or listings)[0].symbol


def _free_ticker(
    desired: str, isin: str | None, listing: InstrumentListing, taken: dict[str, Company]
) -> str:
    """Desired symbol, else the ISIN, else SYMBOL.EXCHANGE (internal key, documented)."""
    for candidate in (desired, isin, f"{listing.symbol}.{listing.exchange}"[:30]):
        if candidate and candidate not in taken:
            return candidate
    raise AppError("directory_conflict", f"cannot assign a ticker for {desired}", 500)


def sync_directory(db: Session, provider: MarketDataProvider) -> SyncReport:
    with _sync_lock:
        return _sync(db, provider)


def _sync(db: Session, provider: MarketDataProvider) -> SyncReport:
    result = provider.fetch_directory()
    instruments = list(
        db.scalars(
            select(Instrument)
            .join(Company)
            .where(Company.market == "IN")
            .options(selectinload(Instrument.company))
        )
    )
    by_isin = {(i.exchange, i.isin): i for i in instruments if i.isin}
    by_symbol = {
        (i.exchange, i.symbol): i
        for i in instruments
        if i.isin is None and i.provider == result.provider
    }
    companies = list(db.scalars(select(Company).where(Company.market == "IN")))
    company_by_isin = {c.isin: c for c in companies if c.isin}
    taken = {c.ticker: c for c in companies}

    groups: dict[str, list[InstrumentListing]] = defaultdict(list)
    for listing in result.listings:
        groups[listing.company_key].append(listing)

    seen: set[int] = set()
    companies_created = instruments_created = renamed = 0
    for listings in groups.values():
        isin = next((listing.isin for listing in listings if listing.isin), None)
        matched = [
            by_isin.get((listing.exchange, listing.isin))
            if listing.isin
            else by_symbol.get((listing.exchange, listing.symbol))
            for listing in listings
        ]
        company = company_by_isin.get(isin) if isin else None
        if company is None:
            company = next((m.company for m in matched if m is not None), None)
        name = max((listing.name for listing in listings), key=len)
        desired = _canonical_symbol(listings)
        if company is None:
            ticker = _free_ticker(desired, isin, listings[0], taken)
            company = Company(market="IN", ticker=ticker, isin=isin, name=name)
            db.add(company)
            taken[ticker] = company
            if isin:
                company_by_isin[isin] = company
            companies_created += 1
        else:
            company.name = name
            if isin and company.isin is None:
                company.isin = isin
            if company.ticker != desired and desired not in taken:
                taken.pop(company.ticker, None)
                company.ticker = desired
                taken[desired] = company

        for listing, instrument in zip(listings, matched, strict=True):
            if instrument is None:
                instrument = Instrument(
                    company=company,
                    exchange=listing.exchange,
                    symbol=listing.symbol,
                    isin=listing.isin,
                    former_symbols=[],
                )
                db.add(instrument)
                instruments_created += 1
            elif instrument.symbol != listing.symbol:
                instrument.former_symbols = [*instrument.former_symbols, instrument.symbol]
                renamed += 1
            instrument.company = company
            instrument.symbol = listing.symbol
            instrument.name = listing.name
            instrument.series = listing.series
            instrument.currency = listing.currency
            instrument.listing_status = "active"
            instrument.provider = result.provider
            instrument.provider_instrument_key = listing.provider_instrument_key
            instrument.last_traded_on = listing.last_traded_on
            instrument.retrieved_at = result.retrieved_at
            seen.add(id(instrument))

    missing = 0
    for instrument in instruments:
        if id(instrument) not in seen and instrument.listing_status != "not_in_latest_snapshot":
            instrument.listing_status = "not_in_latest_snapshot"
            missing += 1
    db.commit()
    report = SyncReport(
        provider=result.provider,
        as_of=result.as_of,
        listings=len(result.listings),
        companies_created=companies_created,
        instruments_created=instruments_created,
        renamed=renamed,
        marked_not_in_snapshot=missing,
    )
    logger.info("instrument_directory_synced", extra=report.__dict__)
    return report


def ensure_directory(db: Session, provider: MarketDataProvider) -> None:
    """Populate the Indian directory on first use (no-op once any instrument exists)."""
    if db.scalar(select(Instrument.id).limit(1)) is not None:
        return
    try:
        sync_directory(db, provider)
    except ProviderError as exc:
        logger.warning("directory_sync_failed", extra={"error": str(exc)})
        raise AppError(
            "provider_unavailable", "Could not load the instrument directory", 502
        ) from None


def resolve_listing(company: Company, exchange: str | None) -> Instrument:
    """The listing a market-data request refers to. Never guesses between exchanges."""
    if exchange is not None:
        on_exchange = [i for i in company.instruments if i.exchange == exchange]
        if not on_exchange:
            raise AppError("listing_not_found", f"{company.ticker} has no {exchange} listing", 404)
        on_exchange.sort(key=lambda i: i.listing_status != "active")
        return on_exchange[0]
    active = [i for i in company.instruments if i.listing_status == "active"]
    candidates = active or company.instruments
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise AppError("listing_not_found", f"{company.ticker} has no exchange listings", 404)
    raise AppError(
        "ambiguous_listing",
        f"{company.ticker} is listed on several exchanges; pass ?exchange=",
        409,
        details={"listings": [{"exchange": i.exchange, "symbol": i.symbol} for i in candidates]},
    )
