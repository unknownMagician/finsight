"""Normalize Yahoo Finance statement tables (as returned by ``yfinance``) into line items.

Pure function, no I/O; the adapter converts yfinance DataFrames to plain dicts first:
``{"annual"|"quarterly": {"income"|"balance"|"cash_flow": {"YYYY-MM-DD": {label: value}}}}``.

Rules (verified against live RELIANCE.NS output from yfinance 1.7.0, 2026-10-18):

1. Values are absolute amounts in the statement currency (``financialCurrency``), so
   ``scale = units``. Per-share values (EPS) and share counts are unscaled.
2. Yahoo does not say whether figures are consolidated or standalone, so ``basis`` is
   ``unspecified`` and a warning says so. The two are never assumed.
3. Fiscal labels: annual columns are fiscal years named by their end year (Indian FY ending
   31 Mar 2026 -> FY2026). The fiscal year-end month is the most common annual column month;
   quarter n is the quarter ending 3n months after the previous year-end. Quarterly columns
   cannot be labelled without annual columns and are skipped with a warning.
4. Missing / NaN cells are absent, never zero. Outflows that Yahoo reports as negative
   (capex, dividends, buybacks) are negated to the domain's positive-magnitude convention; a
   value with the unexpected sign is dropped with a warning by the domain validation.
5. Each item records its Yahoo row label as ``source_concept`` (``yfinance:<label>``).
"""

import math
from collections import Counter
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from app.providers.base import IngestedLineItem, IngestedPeriod, StatementName
from app.providers.normalize_common import validate_statement_items


@dataclass(frozen=True)
class YahooMapping:
    statement: StatementName
    item: str
    labels: tuple[str, ...]  # first label with a value wins
    negate: bool = False  # Yahoo reports this outflow as a negative number


MAPPINGS: tuple[YahooMapping, ...] = (
    YahooMapping("income", "revenue", ("Total Revenue", "Operating Revenue")),
    YahooMapping("income", "cost_of_revenue", ("Cost Of Revenue",)),
    YahooMapping("income", "gross_profit", ("Gross Profit",)),
    YahooMapping("income", "operating_income", ("Operating Income",)),
    YahooMapping("income", "depreciation_amortization", ("Reconciled Depreciation",)),
    YahooMapping("income", "interest_expense", ("Interest Expense",)),
    YahooMapping("income", "pretax_income", ("Pretax Income",)),
    YahooMapping("income", "income_tax_expense", ("Tax Provision",)),
    YahooMapping("income", "net_income", ("Net Income Common Stockholders", "Net Income")),
    YahooMapping("income", "diluted_shares", ("Diluted Average Shares",)),
    YahooMapping("income", "diluted_eps", ("Diluted EPS",)),
    YahooMapping("balance", "cash_and_equivalents", ("Cash And Cash Equivalents",)),
    YahooMapping("balance", "short_term_investments", ("Other Short Term Investments",)),
    YahooMapping("balance", "accounts_receivable", ("Accounts Receivable",)),
    YahooMapping("balance", "inventory", ("Inventory",)),
    YahooMapping("balance", "total_current_assets", ("Current Assets",)),
    YahooMapping("balance", "total_assets", ("Total Assets",)),
    YahooMapping("balance", "accounts_payable", ("Accounts Payable",)),
    YahooMapping("balance", "total_current_liabilities", ("Current Liabilities",)),
    YahooMapping("balance", "short_term_debt", ("Current Debt",)),
    YahooMapping("balance", "long_term_debt", ("Long Term Debt",)),
    # Yahoo's "Total Debt" includes capital lease obligations.
    YahooMapping("balance", "total_debt", ("Total Debt",)),
    YahooMapping("balance", "total_liabilities", ("Total Liabilities Net Minority Interest",)),
    YahooMapping("balance", "total_equity", ("Stockholders Equity",)),
    YahooMapping("balance", "minority_interest", ("Minority Interest",)),
    YahooMapping("balance", "preferred_equity", ("Preferred Stock Equity",)),
    YahooMapping("balance", "shares_outstanding", ("Ordinary Shares Number",)),
    YahooMapping("cash_flow", "operating_cash_flow", ("Operating Cash Flow",)),
    YahooMapping("cash_flow", "capital_expenditures", ("Capital Expenditure",), negate=True),
    YahooMapping("cash_flow", "dividends_paid", ("Cash Dividends Paid",), negate=True),
    YahooMapping("cash_flow", "share_repurchases", ("Repurchase Of Capital Stock",), negate=True),
)

BASIS_WARNING = (
    "Yahoo Finance does not state whether statements are consolidated or standalone; "
    "basis recorded as 'unspecified'"
)


@dataclass(frozen=True)
class NormalizedYahoo:
    periods: list[IngestedPeriod]
    warnings: list[str]


def _to_decimal(raw: Any) -> Decimal | None:
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, float) and (math.isnan(raw) or math.isinf(raw)):
        return None
    try:
        value = Decimal(str(raw))
    except InvalidOperation:
        return None
    return value if value.is_finite() else None


def _parse_columns(table: dict[str, Any]) -> dict[date, dict[str, Any]]:
    out: dict[date, dict[str, Any]] = {}
    for raw_date, rows in table.items():
        try:
            out[date.fromisoformat(str(raw_date)[:10])] = rows or {}
        except ValueError:
            continue
    return out


def fiscal_label(period_end: date, fy_end_month: int) -> tuple[int, str] | None:
    """Fiscal (year, period) for a quarter ending ``period_end``; None if not quarter-aligned."""
    months_after = (period_end.month - fy_end_month) % 12
    if months_after % 3:
        return None
    quarter = months_after // 3 or 4
    fiscal_year = period_end.year if period_end.month <= fy_end_month else period_end.year + 1
    return fiscal_year, f"Q{quarter}"


def normalize_yahoo_statements(
    tables: dict[str, dict[str, dict[str, Any]]], *, currency: str
) -> NormalizedYahoo:
    warnings: list[str] = [BASIS_WARNING]
    annual = {s: _parse_columns(t) for s, t in (tables.get("annual") or {}).items()}
    quarterly = {s: _parse_columns(t) for s, t in (tables.get("quarterly") or {}).items()}

    annual_ends = sorted({d for cols in annual.values() for d in cols}, reverse=True)
    fy_end_month: int | None = None
    if annual_ends:
        fy_end_month = Counter(d.month for d in annual_ends).most_common(1)[0][0]
        for d in annual_ends:
            if d.month != fy_end_month:
                warnings.append(
                    f"annual period ending {d} does not end in month {fy_end_month}; "
                    "possible change of fiscal year-end"
                )

    labelled: list[tuple[str, date, int, str]] = []  # (type, end, fy, fp)
    for d in annual_ends:
        labelled.append(("annual", d, d.year, "FY"))
    quarter_ends = sorted({d for cols in quarterly.values() for d in cols}, reverse=True)
    if quarter_ends and fy_end_month is None:
        warnings.append("quarterly periods skipped: no annual data to infer the fiscal year-end")
    elif fy_end_month is not None:
        for d in quarter_ends:
            fiscal = fiscal_label(d, fy_end_month)
            if fiscal is None:
                warnings.append(f"quarter ending {d} is not aligned to fiscal quarters; skipped")
                continue
            labelled.append(("quarterly", d, fiscal[0], fiscal[1]))

    periods: list[IngestedPeriod] = []
    seen: set[tuple[int, str]] = set()
    for period_type, end, fiscal_year, fiscal_period in labelled:
        name = f"FY{fiscal_year}" if fiscal_period == "FY" else f"{fiscal_period} FY{fiscal_year}"
        if (fiscal_year, fiscal_period) in seen:
            warnings.append(f"{name}: duplicate period ending {end}; skipped")
            continue
        source = annual if period_type == "annual" else quarterly
        by_statement: dict[StatementName, list[IngestedLineItem]] = {}
        for mapping in MAPPINGS:
            rows = (source.get(mapping.statement) or {}).get(end) or {}
            for label in mapping.labels:
                value = _to_decimal(rows.get(label))
                if value is None:
                    continue
                by_statement.setdefault(mapping.statement, []).append(
                    IngestedLineItem(
                        statement=mapping.statement,
                        item=mapping.item,
                        value=-value if mapping.negate else value,
                        source_concept=f"yfinance:{label}",
                        source_accession=None,
                    )
                )
                break
        items: list[IngestedLineItem] = []
        for statement, statement_items in by_statement.items():
            items.extend(validate_statement_items(statement, statement_items, name, warnings))
        if not items:
            continue
        seen.add((fiscal_year, fiscal_period))
        periods.append(
            IngestedPeriod(
                fiscal_year=fiscal_year,
                fiscal_period=fiscal_period,
                period_start=None,  # Yahoo gives period ends only
                period_end=end,
                currency=currency,
                scale="units",
                items=items,
                basis="unspecified",
            )
        )
    return NormalizedYahoo(periods, warnings)
