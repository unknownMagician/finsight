"""Tej API adapter: free, keyless end-of-day NSE/BSE data (https://api.tejhq.dev).

Verified against the published OpenAPI spec (tej-api 0.1.0, ``/openapi.yaml``) and live
responses on 2026-10-18. Only the keyless "Open" tier (₹0, no signup) is used:

- ``GET /v1/status``                       pipeline freshness (latest published trading date)
- ``GET /v1/snapshot/{exchange}?date=``    every symbol's bhavcopy line for one trading date
                                           (symbol, series, isin, name, OHLC, volume, ...)
- ``GET /v1/ohlcv/{exchange}/{symbol}``    EOD OHLCV history (``from``/``to``, inclusive)
- ``GET /v1/actions/{symbol}``             corporate actions on both exchanges

Coverage: NSE from 2010-01-04, BSE from 2024-07-08. Refreshed on trading days ~18:30 IST.
Prices are raw bhavcopy closes, **not adjusted** for splits/bonuses/dividends (adjusted prices
need a free key and are not integrated). Keyless limits: 100 requests / 10 s per IP at the
edge, 120 / min at origin. There are no intraday or live prices.
"""

import logging
import re
import time
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, cast

import httpx

from app.providers.base import (
    Capability,
    CapabilityUnavailableError,
    CorporateAction,
    CorporateActionsResult,
    CorporateActionType,
    DirectoryResult,
    Exchange,
    InstrumentListing,
    PriceBar,
    PriceSeries,
    ProviderError,
    ProviderNotFoundError,
    ProviderRateLimitedError,
    ProviderStatus,
)

logger = logging.getLogger("app.providers.tej")

BASE_URL = "https://api.tejhq.dev"
EXCHANGES: tuple[Exchange, ...] = ("NSE", "BSE")
_SYMBOL_RE = re.compile(r"^[A-Z0-9][A-Z0-9\-&]{0,29}$")  # from the OpenAPI spec
_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
_MAX_RETRY_AFTER = 10.0
_ACTION_TYPES: frozenset[str] = frozenset({"dividend", "split", "bonus", "rights", "merger"})


def _dec(raw: Any) -> Decimal | None:
    if raw is None or isinstance(raw, bool):
        return None
    try:
        value = Decimal(str(raw))
    except InvalidOperation:
        return None
    return value if value.is_finite() else None


def _int(raw: Any) -> int | None:
    return raw if isinstance(raw, int) and not isinstance(raw, bool) else None


def _date(raw: Any) -> date | None:
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        return None


def normalize_symbol(raw: str) -> str | None:
    symbol = raw.strip().upper()
    return symbol if _SYMBOL_RE.match(symbol) else None


def parse_bars(rows: Any) -> tuple[list[PriceBar], list[str]]:
    """Validate OHLCV rows; malformed or internally inconsistent rows are dropped, not fixed."""
    if not isinstance(rows, list):
        raise ProviderError("unexpected OHLCV format")
    bars: dict[date, PriceBar] = {}
    dropped = 0
    for row in rows:
        if not isinstance(row, dict):
            dropped += 1
            continue
        day = _date(row.get("date"))
        o, h, low, c = (_dec(row.get(k)) for k in ("open", "high", "low", "close"))
        if day is None or o is None or h is None or low is None or c is None:
            dropped += 1
            continue
        if min(o, h, low, c) <= 0 or h < low or not (low <= o <= h and low <= c <= h):
            dropped += 1
            continue
        bars[day] = PriceBar(
            date=day,
            open=o,
            high=h,
            low=low,
            close=c,
            volume=_int(row.get("volume")),
            prev_close=_dec(row.get("prev_close")),
            turnover=_dec(row.get("turnover")),
            trades=_int(row.get("trades")),
        )
    warnings = [f"dropped {dropped} malformed or inconsistent price rows"] if dropped else []
    return [bars[d] for d in sorted(bars)], warnings


def parse_snapshot(exchange: Exchange, rows: Any, as_of: date) -> list[InstrumentListing]:
    if not isinstance(rows, list):
        raise ProviderError("unexpected snapshot format")
    listings: dict[str, InstrumentListing] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        symbol = normalize_symbol(str(row.get("symbol") or ""))
        name = str(row.get("name") or "").strip()
        if symbol is None or not name:
            continue
        raw_isin = str(row.get("isin") or "").strip().upper()
        isin = raw_isin if re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]", raw_isin) else None
        listings[symbol] = InstrumentListing(
            exchange=exchange,
            symbol=symbol,
            name=name,
            isin=isin,
            series=(str(row.get("series") or "").strip() or None),
            company_key=isin or f"{exchange}:{symbol}",
            currency="INR",
            last_traded_on=as_of,
        )
    return list(listings.values())


def parse_actions(rows: Any) -> list[CorporateAction]:
    if not isinstance(rows, list):
        raise ProviderError("unexpected corporate actions format")
    out: list[CorporateAction] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        exchange = str(row.get("exchange") or "").upper()
        ex_date = _date(row.get("ex_date"))
        if exchange not in EXCHANGES or ex_date is None:
            continue
        raw_type = str(row.get("type") or "").lower()
        out.append(
            CorporateAction(
                exchange=exchange,
                symbol=str(row.get("symbol") or ""),
                isin=(str(row.get("isin")) if row.get("isin") else None),
                ex_date=ex_date,
                record_date=_date(row.get("record_date")),
                action_type=cast(
                    CorporateActionType, raw_type if raw_type in _ACTION_TYPES else "other"
                ),
                ratio_numerator=_int(row.get("ratio_num")),
                ratio_denominator=_int(row.get("ratio_den")),
                cash_amount=_dec(row.get("cash_amount")),
                face_value_from=_dec(row.get("face_value_from")),
                face_value_to=_dec(row.get("face_value_to")),
                description=str(row.get("raw_subject") or ""),
            )
        )
    out.sort(key=lambda a: (a.ex_date, a.exchange), reverse=True)
    return out


class TejMarketDataProvider:
    name = "tej"
    capabilities = frozenset(
        {Capability.INSTRUMENT_DIRECTORY, Capability.EOD_PRICES, Capability.CORPORATE_ACTIONS}
    )

    def __init__(
        self,
        *,
        base_url: str = BASE_URL,
        timeout: float = 15.0,
        max_retries: int = 3,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self._base_url,
            headers={"Accept": "application/json", "User-Agent": "FinSight (tej-api client)"},
            timeout=timeout,
            transport=transport,
            follow_redirects=False,
        )
        self._max_retries = max_retries
        self._sleep = sleep

    def close(self) -> None:
        self._client.close()

    def _url(self, path: str) -> str:
        return f"{self._base_url}{path}"

    def _get(self, path: str, params: dict[str, str] | None = None) -> Any:
        attempt = 0
        while True:
            try:
                response = self._client.get(path, params=params)
            except httpx.TransportError as exc:
                if attempt >= self._max_retries:
                    raise ProviderError(f"Tej API unreachable: {type(exc).__name__}") from exc
                delay = 0.5 * 2**attempt
            else:
                status = response.status_code
                if response.is_success:
                    try:
                        return response.json()
                    except ValueError as exc:
                        raise ProviderError("Tej API returned malformed JSON") from exc
                if status in (400, 404):
                    raise ProviderNotFoundError(f"Tej API has no data for {path} ({status})")
                if status in (401, 402):
                    # Keyed / paid endpoints; this adapter only calls keyless ones.
                    raise CapabilityUnavailableError(f"Tej API {path} needs a key ({status})")
                if status not in _RETRY_STATUSES or attempt >= self._max_retries:
                    if status == 429:
                        raise ProviderRateLimitedError("Tej API rate limit exceeded")
                    raise ProviderError(f"Tej API responded {status}")
                delay = 0.5 * 2**attempt
                retry_after = response.headers.get("Retry-After", "")
                if retry_after.isdigit():
                    delay = min(float(retry_after), _MAX_RETRY_AFTER)
            attempt += 1
            logger.warning("tej_retry", extra={"path": path, "attempt": attempt})
            self._sleep(delay)

    @staticmethod
    def _data(payload: Any) -> Any:
        if not isinstance(payload, dict) or "data" not in payload:
            raise ProviderError("unexpected Tej API envelope")
        return payload["data"]

    def status(self) -> ProviderStatus:
        try:
            payload = self._get("/v1/status")
        except ProviderError as exc:
            return ProviderStatus(self.name, False, None, None, detail=type(exc).__name__)
        if not isinstance(payload, dict):
            return ProviderStatus(self.name, False, None, None, detail="unexpected status format")
        published = payload.get("prices_published_at")
        try:
            published_at = datetime.fromisoformat(str(published)) if published else None
        except ValueError:
            published_at = None
        return ProviderStatus(
            provider=self.name,
            reachable=True,
            latest_trading_date=_date(payload.get("trading_date")),
            published_at=published_at,
        )

    def fetch_directory(self) -> DirectoryResult:
        status = self.status()
        if not status.reachable or status.latest_trading_date is None:
            raise ProviderError("Tej API status unavailable; cannot pick a snapshot date")
        as_of = status.latest_trading_date
        retrieved_at = datetime.now(UTC)
        listings: list[InstrumentListing] = []
        urls: list[str] = []
        for exchange in EXCHANGES:
            path = f"/v1/snapshot/{exchange.lower()}"
            rows = self._data(self._get(path, {"date": as_of.isoformat()}))
            listings.extend(parse_snapshot(exchange, rows, as_of))
            urls.append(f"{self._url(path)}?date={as_of.isoformat()}")
        return DirectoryResult(self.name, listings, as_of, retrieved_at, urls)

    def fetch_eod_bars(
        self, exchange: Exchange, symbol: str, start: date, end: date
    ) -> PriceSeries:
        normalized = normalize_symbol(symbol)
        if normalized is None:
            raise ProviderNotFoundError(f"invalid symbol {symbol!r}")
        path = f"/v1/ohlcv/{exchange.lower()}/{normalized}"
        params = {"from": start.isoformat(), "to": end.isoformat()}
        retrieved_at = datetime.now(UTC)
        bars, warnings = parse_bars(self._data(self._get(path, params)))
        return PriceSeries(
            provider=self.name,
            exchange=exchange,
            symbol=normalized,
            currency="INR",
            nature="end_of_day",
            adjusted=False,
            bars=bars,
            retrieved_at=retrieved_at,
            source_url=f"{self._url(path)}?from={params['from']}&to={params['to']}",
            warnings=warnings,
        )

    def fetch_corporate_actions(self, symbol: str) -> CorporateActionsResult:
        normalized = normalize_symbol(symbol)
        if normalized is None:
            raise ProviderNotFoundError(f"invalid symbol {symbol!r}")
        path = f"/v1/actions/{normalized}"
        retrieved_at = datetime.now(UTC)
        actions = parse_actions(self._data(self._get(path)))
        return CorporateActionsResult(self.name, actions, retrieved_at, self._url(path))
