"""SYNTHETIC fixtures in the exact shapes of the Tej API and yfinance (verified live on
2026-10-18). Values are invented; identifiers use the unassigned ``ZZ`` ISIN prefix so they
cannot collide with a real security.
"""

from typing import Any

ALPHA_ISIN = "ZZTEST000011"  # listed on NSE and BSE
BETA_ISIN = "ZZTEST000029"  # NSE "BETA"
GAMMA_ISIN = "ZZTEST000037"  # BSE "BETA" - a *different* company with the same symbol
TRADING_DATE = "2026-10-16"

STATUS = {
    "trading_date": TRADING_DATE,
    "stage": "derived",
    "prices_published_at": "2026-10-16T19:27:03Z",
    "derived_published_at": "2026-10-16T19:36:17Z",
    "run_url": None,
    "generated_at": "2026-10-16T19:36:17Z",
}


def _snap(symbol: str, series: str, isin: str, name: str, close: float) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "series": series,
        "isin": isin,
        "name": name,
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "last": close,
        "prev_close": close,
        "volume": 1000,
        "turnover": close * 1000,
        "trades": 10,
    }


SNAPSHOT_NSE = {
    "data": [
        _snap("ALPHA", "EQ", ALPHA_ISIN, "ALPHA INDUSTRIES LTD", 1025.5),
        _snap("BETA", "EQ", BETA_ISIN, "BETA POWER LTD.", 18.69),
        _snap("M&M", "EQ", "ZZTEST000045", "M AND M TEST LTD", 3000.0),
        {"symbol": "", "series": "EQ", "isin": "ZZTEST000052", "name": "NO SYMBOL"},
        _snap("NOISIN", "BE", "not-an-isin", "NO ISIN LTD", 5.0),
    ],
    "meta": {"count": 5, "date": TRADING_DATE, "exchange": "NSE"},
}
SNAPSHOT_BSE = {
    "data": [
        _snap("ALPHA", "A", ALPHA_ISIN, "ALPHA INDUSTRIES LIMITED", 1024.0),
        _snap("BETA", "B", GAMMA_ISIN, "GAMMA TRADERS LTD", 45.0),
    ],
    "meta": {"count": 2, "date": TRADING_DATE, "exchange": "BSE"},
}

OHLCV = {
    "data": [
        {
            "date": "2026-10-14",
            "open": 1000,
            "high": 1020,
            "low": 990.5,
            "close": 1010.0,
            "last": 1010.0,
            "prev_close": 1000.0,
            "volume": 1000000,
            "turnover": 1010000000.0,
            "trades": 20000,
        },
        {  # inconsistent: high < low -> dropped
            "date": "2026-10-15",
            "open": 1010.0,
            "high": 990,
            "low": 1005.0,
            "close": 1015.0,
            "last": 1015.0,
            "prev_close": 1010.0,
            "volume": 1,
            "turnover": 1,
            "trades": 1,
        },
        {
            "date": "2026-10-16",
            "open": 1010.0,
            "high": 1030.25,
            "low": 1001.0,
            "close": 1025.5,
            "last": 1025.5,
            "prev_close": 1010.0,
            "volume": 2000000,
            "turnover": 2051000000.0,
            "trades": 30000,
        },
    ],
    "meta": {"count": 3, "exchange": "NSE", "symbol": "ALPHA"},
}

ACTIONS = {
    "data": [
        {
            "exchange": "NSE",
            "symbol": "ALPHA",
            "isin": ALPHA_ISIN,
            "company": "Alpha Industries Limited",
            "ex_date": "2026-06-05",
            "record_date": "2026-06-05",
            "type": "dividend",
            "cash_amount": 6,
            "raw_subject": "Dividend - Rs 6 Per Share",
        },
        {
            "exchange": "BSE",
            "symbol": "ALPHA",
            "isin": ALPHA_ISIN,
            "company": "Alpha Industries Ltd",
            "ex_date": "2026-06-05",
            "record_date": "2026-06-05",
            "type": "dividend",
            "cash_amount": 6,
            "raw_subject": "Final Dividend - Rs. - 6.0000",
        },
        {
            "exchange": "NSE",
            "symbol": "ALPHA",
            "isin": ALPHA_ISIN,
            "company": "Alpha Industries Limited",
            "ex_date": "2024-10-28",
            "record_date": "2024-10-28",
            "type": "bonus",
            "ratio_num": 1,
            "ratio_den": 1,
            "raw_subject": "Bonus 1:1",
        },
        {
            "exchange": "NSE",
            "symbol": "ALPHA",
            "isin": ALPHA_ISIN,
            "company": "Alpha Industries Limited",
            "ex_date": "2023-07-20",
            "type": "demerger",
            "raw_subject": "Demerger",
        },
    ],
    "meta": {"count": 4, "symbol": "ALPHA"},
}


# yfinance tables after DataFrame -> dict conversion ({period_end: {row label: value}}).
# NaN appears where Yahoo has no value.
NAN = float("nan")
YAHOO_TABLES: dict[str, dict[str, dict[str, Any]]] = {
    "annual": {
        "income": {
            "2026-03-31": {
                "Total Revenue": 10000000000000.0,
                "Cost Of Revenue": 7500000000000.0,
                "Gross Profit": 2500000000000.0,
                "Operating Income": 1200000000000.0,
                "Reconciled Depreciation": 500000000000.0,
                "Interest Expense": 200000000000.0,
                "Pretax Income": 1100000000000.0,
                "Tax Provision": 275000000000.0,
                "Net Income Common Stockholders": 800000000000.0,
                "Diluted Average Shares": 13500000000.0,
                "Diluted EPS": 59.25,
            },
            "2025-03-31": {"Total Revenue": 9500000000000.0, "Net Income": 700000000000.0},
        },
        "balance": {
            "2026-03-31": {
                "Cash And Cash Equivalents": 1300000000000.0,
                "Total Debt": 4000000000000.0,
                "Stockholders Equity": 9000000000000.0,
                "Minority Interest": 1800000000000.0,
                "Ordinary Shares Number": 13500000000.0,
                "Inventory": NAN,
            }
        },
        "cash_flow": {
            "2026-03-31": {
                "Operating Cash Flow": 1900000000000.0,
                "Capital Expenditure": -1200000000000.0,
                "Cash Dividends Paid": -75000000000.0,
            },
            "2025-03-31": {"Capital Expenditure": 5.0},  # wrong sign -> dropped with warning
        },
    },
    "quarterly": {
        "income": {
            "2026-06-30": {"Total Revenue": 3000000000000.0, "Diluted EPS": 15.5},
            "2026-03-31": {"Total Revenue": 2900000000000.0},
            "2025-12-31": {"Total Revenue": 2800000000000.0},
            "2025-11-30": {"Total Revenue": 1.0},  # not quarter-aligned -> skipped
        }
    },
}
