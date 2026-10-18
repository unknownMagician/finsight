"""Operational commands.

python -m app.cli sync-instruments              # IN: load the NSE/BSE directory (market provider)
python -m app.cli ingest RELIANCE TCS           # IN: statements via the fundamentals provider
python -m app.cli sync-companies                # US: load the SEC company directory
python -m app.cli ingest --market US AAPL MSFT  # US: annual financials from SEC EDGAR
"""

import argparse
import sys

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging import configure_logging
from app.db.session import get_sessionmaker
from app.providers.base import ProviderError
from app.providers.demo import DemoMarketDataProvider
from app.providers.registry import (
    ProviderConfigError,
    build_fundamentals_provider,
    build_market_provider,
)
from app.providers.sec_edgar import SecEdgarProvider
from app.services import companies, instruments


def _sec_provider() -> SecEdgarProvider | None:
    settings = get_settings()
    if not settings.sec_user_agent:
        print("FINSIGHT_SEC_USER_AGENT must be set (e.g. 'FinSight you@example.com')")
        return None
    return SecEdgarProvider(settings.sec_user_agent, timeout=settings.sec_timeout_seconds)


def _run_us(command: str, tickers: list[str]) -> int:
    provider = _sec_provider()
    if provider is None:
        return 2
    try:
        with get_sessionmaker()() as db:
            if command == "sync-companies":
                print(f"synced {companies.sync_directory(db, provider)} companies")
                return 0
            for ticker in tickers:
                try:
                    company, result = companies.ingest(db, provider, ticker)
                except AppError as exc:
                    print(f"{ticker}: {exc.code} - {exc.message}")
                    continue
                years = ", ".join(str(p.fiscal_year) for p in result.periods)
                print(f"{company.ticker}: {len(result.periods)} periods ({years})")
                for warning in result.warnings:
                    print(f"  warning: {warning}")
    finally:
        provider.close()
    return 0


def _run_in(command: str, tickers: list[str]) -> int:
    settings = get_settings()
    demo = DemoMarketDataProvider()
    market = build_market_provider(settings, demo)
    try:
        with get_sessionmaker()() as db:
            if command == "sync-instruments":
                try:
                    report = instruments.sync_directory(db, market)
                except ProviderError as exc:
                    print(f"directory sync failed: {exc}")
                    return 1
                print(
                    f"{report.provider} snapshot {report.as_of}: {report.listings} listings, "
                    f"{report.companies_created} new companies, {report.renamed} renames, "
                    f"{report.marked_not_in_snapshot} not in snapshot"
                )
                return 0
            try:
                fundamentals = build_fundamentals_provider(settings, demo)
            except ProviderConfigError as exc:
                print(str(exc))
                return 2
            if fundamentals is None:
                print("FINSIGHT_FUNDAMENTALS_PROVIDER=none: statement ingestion is disabled")
                return 2
            instruments.ensure_directory(db, market)
            for ticker in tickers:
                try:
                    company = companies.get_company(db, ticker, "IN")
                    result = companies.ingest_india(db, fundamentals, company)
                except AppError as exc:
                    print(f"{ticker}: {exc.code} - {exc.message}")
                    continue
                labels = ", ".join(
                    f"{p.fiscal_period} FY{p.fiscal_year} {p.basis}" for p in result.periods
                )
                print(f"{company.ticker}: {len(result.periods)} periods ({labels})")
                for warning in result.warnings:
                    print(f"  warning: {warning}")
    finally:
        market.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("sync-instruments", help="load the NSE/BSE instrument directory (IN)")
    sub.add_parser("sync-companies", help="load the SEC ticker directory (US)")
    ingest = sub.add_parser("ingest", help="ingest financial statements for tickers")
    ingest.add_argument("--market", choices=("IN", "US"), default=None)
    ingest.add_argument("tickers", nargs="+")
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    if args.command == "sync-companies":
        return _run_us(args.command, [])
    if args.command == "sync-instruments":
        return _run_in(args.command, [])
    market = args.market or settings.default_market
    return (_run_us if market == "US" else _run_in)(args.command, args.tickers)


if __name__ == "__main__":
    sys.exit(main())
