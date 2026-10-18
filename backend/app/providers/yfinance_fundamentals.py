"""Yahoo Finance statements via the unofficial ``yfinance`` library (optional extra).

``yfinance`` is not affiliated with or endorsed by Yahoo; its README states the Yahoo Finance
API is "intended for personal use only". It scrapes Yahoo endpoints that can change or rate
limit without notice. Treat this adapter as best-effort and personal-use only; it is off by
default (``FINSIGHT_FUNDAMENTALS_PROVIDER=yfinance`` enables it) and is never used in tests.

Symbol mapping: NSE listing -> ``<SYMBOL>.NS``; BSE listing -> ``<SYMBOL>.BO`` (verified to
work for symbol-style BSE tickers such as RELIANCE.BO; Yahoo does not accept every BSE
scrip). The NSE listing is preferred when a company has both.
"""

import importlib
import importlib.util
import logging
import math
from datetime import UTC, datetime
from typing import Any

from app.providers.base import (
    Capability,
    IngestionResult,
    InstrumentRef,
    ProviderError,
    ProviderNotFoundError,
    ProviderRateLimitedError,
)
from app.providers.yfinance_normalize import normalize_yahoo_statements

logger = logging.getLogger("app.providers.yfinance")

_SUFFIX = {"NSE": ".NS", "BSE": ".BO"}
_FRAMES = {
    "annual": {"income": "income_stmt", "balance": "balance_sheet", "cash_flow": "cashflow"},
    "quarterly": {
        "income": "quarterly_income_stmt",
        "balance": "quarterly_balance_sheet",
        "cash_flow": "quarterly_cashflow",
    },
}


def yfinance_available() -> bool:
    return importlib.util.find_spec("yfinance") is not None


def yahoo_symbol(ref: InstrumentRef) -> str:
    return f"{ref.symbol}{_SUFFIX[ref.exchange]}"


def _frame_to_dict(frame: Any) -> dict[str, dict[str, Any]]:
    """DataFrame (rows = labels, columns = period-end timestamps) -> {date: {label: value}}."""
    if frame is None or getattr(frame, "empty", True):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for column in frame.columns:
        key = column.date().isoformat() if hasattr(column, "date") else str(column)[:10]
        values: dict[str, Any] = {}
        for label, value in frame[column].items():
            if isinstance(value, float) and math.isnan(value):
                continue
            values[str(label)] = value.item() if hasattr(value, "item") else value
        out[key] = values
    return out


class YFinanceFundamentalsProvider:
    name = "yfinance"
    capabilities = frozenset({Capability.FINANCIAL_STATEMENTS})

    def __init__(self) -> None:
        if not yfinance_available():
            raise RuntimeError("yfinance is not installed (pip install -e '.[yfinance]')")
        self._yf = importlib.import_module("yfinance")

    def close(self) -> None:
        return None

    def fetch_financials(self, ref: InstrumentRef) -> IngestionResult:
        symbol = yahoo_symbol(ref)
        retrieved_at = datetime.now(UTC)
        try:
            ticker = self._yf.Ticker(symbol)
            tables = {
                period_type: {
                    statement: _frame_to_dict(getattr(ticker, attr))
                    for statement, attr in frames.items()
                }
                for period_type, frames in _FRAMES.items()
            }
            currency = (ticker.info or {}).get("financialCurrency")
        except Exception as exc:  # yfinance raises many unrelated exception types
            if "RateLimit" in type(exc).__name__:
                raise ProviderRateLimitedError("Yahoo Finance rate limit") from exc
            logger.warning("yfinance_error", extra={"symbol": symbol, "error": repr(exc)})
            raise ProviderError(f"yfinance failed for {symbol}") from exc

        if not any(t for frames in tables.values() for t in frames.values()):
            raise ProviderNotFoundError(f"Yahoo Finance has no statements for {symbol}")
        if not isinstance(currency, str) or len(currency) != 3:
            raise ProviderError(f"Yahoo Finance did not report a statement currency for {symbol}")

        normalized = normalize_yahoo_statements(tables, currency=currency.upper())
        return IngestionResult(
            provider=self.name,
            source_url=f"https://finance.yahoo.com/quote/{symbol}/financials",
            retrieved_at=retrieved_at,
            entity_name=None,
            periods=normalized.periods,
            warnings=normalized.warnings,
        )
