"""SEC EDGAR provider: company directory + XBRL companyfacts over HTTPS.

SEC fair-access policy: a descriptive User-Agent with contact details is mandatory and request
rates must stay under 10/s. Requests here are on-demand and low volume.
"""

import logging
import re
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx

from app.providers.base import (
    CompanyListing,
    IngestionResult,
    ProviderError,
    ProviderNotFoundError,
)
from app.providers.edgar_normalize import normalize_companyfacts

logger = logging.getLogger("app.providers.sec_edgar")

TICKERS_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
_DIRECTORY_TTL_SECONDS = 24 * 3600
_MAX_RETRY_AFTER = 10.0
_TICKER_RE = re.compile(r"^[A-Z0-9.\-]{1,20}$")


def normalize_ticker(raw: str) -> str | None:
    ticker = raw.strip().upper()
    return ticker if _TICKER_RE.match(ticker) else None


class SecEdgarProvider:
    name = "sec_edgar"

    def __init__(
        self,
        user_agent: str,
        *,
        timeout: float = 15.0,
        max_retries: int = 3,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not user_agent.strip():
            raise ValueError("SEC requires a User-Agent with contact information")
        self._client = httpx.Client(
            headers={"User-Agent": user_agent, "Accept": "application/json"},
            timeout=timeout,
            transport=transport,
            follow_redirects=False,
        )
        self._max_retries = max_retries
        self._sleep = sleep
        self._directory: dict[str, CompanyListing] | None = None
        self._directory_loaded_at = 0.0
        self._lock = threading.Lock()

    def close(self) -> None:
        self._client.close()

    # --- HTTP -------------------------------------------------------------------------------

    def _get_json(self, url: str) -> Any:
        attempt = 0
        while True:
            try:
                response = self._client.get(url)
            except httpx.TransportError as exc:
                if attempt >= self._max_retries:
                    raise ProviderError(f"SEC EDGAR unreachable: {type(exc).__name__}") from exc
                delay = 0.5 * 2**attempt
            else:
                if response.status_code == 404:
                    raise ProviderNotFoundError(f"SEC EDGAR has no data at {url}")
                if response.status_code in _RETRY_STATUSES and attempt < self._max_retries:
                    delay = 0.5 * 2**attempt
                    retry_after = response.headers.get("Retry-After", "")
                    if retry_after.isdigit():
                        delay = min(float(retry_after), _MAX_RETRY_AFTER)
                elif response.is_success:
                    try:
                        return response.json()
                    except ValueError as exc:
                        raise ProviderError("SEC EDGAR returned malformed JSON") from exc
                else:
                    raise ProviderError(f"SEC EDGAR responded {response.status_code}")
            attempt += 1
            logger.warning("sec_edgar_retry", extra={"url": url, "attempt": attempt})
            self._sleep(delay)

    # --- Directory ----------------------------------------------------------------------------

    def _load_directory(self) -> dict[str, CompanyListing]:
        with self._lock:
            fresh = time.monotonic() - self._directory_loaded_at < _DIRECTORY_TTL_SECONDS
            if self._directory is not None and fresh:
                return self._directory
            payload = self._get_json(TICKERS_URL)
            try:
                fields = payload["fields"]
                idx = {name: fields.index(name) for name in ("cik", "name", "ticker", "exchange")}
                rows = payload["data"]
            except (KeyError, TypeError, ValueError) as exc:
                raise ProviderError("unexpected SEC ticker directory format") from exc
            directory: dict[str, CompanyListing] = {}
            for row in rows:
                ticker = normalize_ticker(str(row[idx["ticker"]] or ""))
                if ticker is None or ticker in directory:
                    continue
                directory[ticker] = CompanyListing(
                    ticker=ticker,
                    cik=f"{int(row[idx['cik']]):010d}",
                    name=str(row[idx["name"]]),
                    exchange=row[idx["exchange"]] or None,
                )
            self._directory = directory
            self._directory_loaded_at = time.monotonic()
            return directory

    def list_companies(self) -> list[CompanyListing]:
        return list(self._load_directory().values())

    def lookup(self, ticker: str) -> CompanyListing | None:
        normalized = normalize_ticker(ticker)
        return self._load_directory().get(normalized) if normalized else None

    # --- Financials -------------------------------------------------------------------------

    def fetch_annual_financials(self, listing: CompanyListing) -> IngestionResult:
        url = FACTS_URL.format(cik=listing.cik)
        retrieved_at = datetime.now(UTC)
        doc = self._get_json(url)
        if not isinstance(doc, dict):
            raise ProviderError("unexpected companyfacts format")
        normalized = normalize_companyfacts(doc)
        return IngestionResult(
            provider=self.name,
            source_url=url,
            retrieved_at=retrieved_at,
            entity_name=normalized.entity_name,
            periods=normalized.periods,
            warnings=normalized.warnings,
        )
