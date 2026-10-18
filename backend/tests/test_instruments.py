"""Instrument directory sync and listing resolution (identity rules for NSE/BSE)."""

from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.session import get_sessionmaker
from app.models import Company, Instrument
from app.providers.base import Capability, DirectoryResult, InstrumentListing
from app.providers.tej import parse_snapshot
from app.services import companies, instruments
from tests import fixtures_india as fx

AS_OF = date(2026, 10, 16)


class DirectoryProvider:
    name = "tej"
    capabilities = frozenset({Capability.INSTRUMENT_DIRECTORY})

    def __init__(self, listings: list[InstrumentListing]) -> None:
        self.listings = listings

    def fetch_directory(self) -> DirectoryResult:
        return DirectoryResult(
            self.name, self.listings, AS_OF, datetime(2026, 10, 16, 14, tzinfo=UTC), []
        )


def tej_listings() -> list[InstrumentListing]:
    return parse_snapshot("NSE", fx.SNAPSHOT_NSE["data"], AS_OF) + parse_snapshot(
        "BSE", fx.SNAPSHOT_BSE["data"], AS_OF
    )


@pytest.fixture
def db(migrated: None) -> Iterator[Session]:
    with get_sessionmaker()() as session:
        yield session


def by_ticker(db: Session) -> dict[str, Company]:
    return {c.ticker: c for c in db.scalars(select(Company).where(Company.market == "IN"))}


def test_cross_listed_company_is_one_company_with_two_instruments(db: Session) -> None:
    report = instruments.sync_directory(db, DirectoryProvider(tej_listings()))
    assert (report.listings, report.companies_created, report.instruments_created) == (6, 5, 6)
    found = by_ticker(db)
    alpha = found["ALPHA"]
    assert alpha.isin == fx.ALPHA_ISIN
    assert alpha.name == "ALPHA INDUSTRIES LIMITED"  # longest exchange name
    assert {(i.exchange, i.series) for i in alpha.instruments} == {("NSE", "EQ"), ("BSE", "A")}
    # NSE "BETA" and BSE "BETA" are different ISINs, so different companies; the BSE-only
    # company cannot take the ticker and falls back to its real ISIN.
    assert found["BETA"].isin == fx.BETA_ISIN
    assert found[fx.GAMMA_ISIN].name == "GAMMA TRADERS LTD"
    assert found["NOISIN"].isin is None  # missing/malformed ISIN is never invented
    assert "M&M" in found


def test_resync_is_idempotent_and_tracks_renames_and_gaps(db: Session) -> None:
    provider = DirectoryProvider(tej_listings())
    instruments.sync_directory(db, provider)
    again = instruments.sync_directory(db, provider)
    assert (again.companies_created, again.instruments_created, again.renamed) == (0, 0, 0)

    # ALPHA is renamed to ALPHANEW on NSE (same ISIN); M&M did not trade this day.
    renamed = [
        replace(x, symbol="ALPHANEW") if (x.exchange, x.symbol) == ("NSE", "ALPHA") else x
        for x in tej_listings()
        if x.symbol != "M&M"
    ]
    report = instruments.sync_directory(db, DirectoryProvider(renamed))
    assert (report.renamed, report.marked_not_in_snapshot) == (1, 1)
    db.expire_all()
    found = by_ticker(db)
    assert "ALPHANEW" in found and "ALPHA" not in found  # ticker follows the NSE symbol
    nse = next(i for i in found["ALPHANEW"].instruments if i.exchange == "NSE")
    assert nse.former_symbols == ["ALPHA"]
    mm = db.scalar(select(Instrument).where(Instrument.symbol == "M&M"))
    assert mm is not None and mm.listing_status == "not_in_latest_snapshot"

    # Search still finds the company by its ISIN or any listing symbol.
    assert [c.ticker for c in companies.search(db, fx.ALPHA_ISIN, market="IN")] == ["ALPHANEW"]
    assert companies.get_company(db, fx.ALPHA_ISIN.lower(), "IN").ticker == "ALPHANEW"


def test_resolve_listing(db: Session) -> None:
    instruments.sync_directory(db, DirectoryProvider(tej_listings()))
    alpha = companies.get_company(db, "ALPHA", "IN")
    with pytest.raises(AppError) as exc:
        instruments.resolve_listing(alpha, None)
    assert exc.value.code == "ambiguous_listing" and exc.value.status_code == 409
    assert instruments.resolve_listing(alpha, "BSE").exchange == "BSE"
    beta = companies.get_company(db, "BETA", "IN")
    assert instruments.resolve_listing(beta, None).exchange == "NSE"
    with pytest.raises(AppError) as exc:
        instruments.resolve_listing(beta, "BSE")
    assert exc.value.code == "listing_not_found"


def test_us_and_indian_companies_coexist(db: Session) -> None:
    instruments.sync_directory(db, DirectoryProvider(tej_listings()))
    db.add(Company(market="US", ticker="ALPHA", cik="0000000001", name="Alpha Corp (US)"))
    db.commit()  # same ticker, different market: allowed
    assert companies.get_company(db, "ALPHA", "US").name == "Alpha Corp (US)"
    assert companies.get_company(db, "ALPHA", "IN").isin == fx.ALPHA_ISIN
