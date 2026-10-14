"""Operational commands.

python -m app.cli sync-companies      # load the SEC company directory into `companies`
python -m app.cli ingest AAPL MSFT    # fetch annual financials for tickers
"""

import argparse
import sys

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging import configure_logging
from app.db.session import get_sessionmaker
from app.providers.sec_edgar import SecEdgarProvider
from app.services import companies


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("sync-companies", help="load the SEC ticker directory")
    ingest = sub.add_parser("ingest", help="ingest annual financials for tickers")
    ingest.add_argument("tickers", nargs="+")
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    if not settings.sec_user_agent:
        print("FINSIGHT_SEC_USER_AGENT must be set (e.g. 'FinSight you@example.com')")
        return 2
    provider = SecEdgarProvider(settings.sec_user_agent, timeout=settings.sec_timeout_seconds)
    try:
        with get_sessionmaker()() as db:
            if args.command == "sync-companies":
                print(f"synced {companies.sync_directory(db, provider)} companies")
            else:
                for ticker in args.tickers:
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


if __name__ == "__main__":
    sys.exit(main())
