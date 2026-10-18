"""Deterministic synthetic Indian-market data for development, demos and tests.

Everything here is fabricated on purpose and labelled as such: the provider name is ``demo``,
company names start with "Demo", price data is tagged ``nature="demo"`` and statements are
``basis``-tagged synthetic figures. No ISINs are produced (inventing identifiers that look real
is not allowed); listings are grouped by a provider-scoped ``demo:<n>`` key instead.

The data is a pure function of its inputs (symbol, dates), with no randomness and no network,
so tests can assert exact values. ``today`` is injectable.

Scenarios covered:
- DEMOINFO: listed on NSE and BSE (same company), consolidated + standalone statements,
  regular dividends.
- DEMOSTEEL: NSE only, loss-making latest year (P/E not meaningful), split before the period.
- DEMOBANK: BSE only, standalone statements only.
- DEMOAGRO: the NSE symbol and the BSE symbol "DEMOAGRO" belong to *different* companies,
  and the NSE company had a bonus issue after its latest fiscal year-end.
"""

import hashlib
import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from app.providers.base import (
    Capability,
    CorporateAction,
    CorporateActionsResult,
    DirectoryResult,
    Exchange,
    IngestedLineItem,
    IngestedPeriod,
    IngestionResult,
    InstrumentListing,
    InstrumentRef,
    PriceBar,
    PriceSeries,
    ProviderNotFoundError,
    ProviderStatus,
)
from app.providers.normalize_common import validate_statement_items

NAME = "demo"
FIRST_DATE = date(2020, 1, 1)
TICK = Decimal("0.05")


@dataclass(frozen=True)
class _DemoCompany:
    key: str
    name: str
    listings: tuple[tuple[Exchange, str, str], ...]  # (exchange, symbol, series)
    base_price: float
    revenue_cr: Decimal  # latest FY revenue, ₹ crore
    growth: Decimal
    net_margin: Decimal
    shares: int
    bases: tuple[str, ...]
    loss_latest_year: bool = False


COMPANIES: tuple[_DemoCompany, ...] = (
    _DemoCompany(
        "demo:1",
        "Demo Infotech Ltd",
        (("NSE", "DEMOINFO", "EQ"), ("BSE", "DEMOINFO", "A")),
        1500.0,
        Decimal(12000),
        Decimal("0.10"),
        Decimal("0.18"),
        400_000_000,
        ("consolidated", "standalone"),
    ),
    _DemoCompany(
        "demo:2",
        "Demo Steel Ltd",
        (("NSE", "DEMOSTEEL", "EQ"),),
        140.0,
        Decimal(30000),
        Decimal("0.04"),
        Decimal("0.03"),
        2_500_000_000,
        ("consolidated",),
        loss_latest_year=True,
    ),
    _DemoCompany(
        "demo:3",
        "Demo Bank Ltd",
        (("BSE", "DEMOBANK", "A"),),
        620.0,
        Decimal(8000),
        Decimal("0.12"),
        Decimal("0.22"),
        900_000_000,
        ("standalone",),
    ),
    _DemoCompany(
        "demo:4",
        "Demo Agro Industries Ltd",
        (("NSE", "DEMOAGRO", "EQ"),),
        310.0,
        Decimal(2500),
        Decimal("0.08"),
        Decimal("0.07"),
        150_000_000,
        ("consolidated",),
    ),
    _DemoCompany(
        "demo:5",
        "Demo Agrochem Traders Ltd",
        (("BSE", "DEMOAGRO", "B"),),
        45.0,
        Decimal(300),
        Decimal("0.05"),
        Decimal("0.04"),
        60_000_000,
        ("standalone",),
    ),
)


def _noise(*parts: object) -> float:
    """Deterministic value in [-1, 1) derived from the inputs."""
    digest = hashlib.sha256("|".join(map(str, parts)).encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**63 - 1.0


def _tick(value: float) -> Decimal:
    return (Decimal(str(value)) / TICK).quantize(Decimal(1), ROUND_HALF_UP) * TICK


def _previous_weekday(day: date) -> date:
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def _latest_completed_fy_end(today: date) -> date:
    """Indian fiscal year ends 31 March; statements are 'available' two months later."""
    year = today.year if today >= date(today.year, 6, 1) else today.year - 1
    return date(year, 3, 31)


class DemoMarketDataProvider:
    """Implements both ``MarketDataProvider`` and ``FundamentalsProvider``."""

    name = NAME
    capabilities = frozenset(
        {
            Capability.INSTRUMENT_DIRECTORY,
            Capability.EOD_PRICES,
            Capability.CORPORATE_ACTIONS,
            Capability.FINANCIAL_STATEMENTS,
        }
    )

    def __init__(self, today: Callable[[], date] | None = None) -> None:
        self._today = today or (lambda: datetime.now(UTC).date())

    def close(self) -> None:
        return None

    # --- helpers -------------------------------------------------------------------------------

    def _as_of(self) -> date:
        # Data for a trading day is "published" after the close; use the previous weekday.
        return _previous_weekday(self._today() - timedelta(days=1))

    def _retrieved_at(self) -> datetime:
        return datetime.combine(self._as_of(), time(13, 0), tzinfo=UTC)

    @staticmethod
    def _find(exchange: Exchange, symbol: str) -> _DemoCompany:
        for company in COMPANIES:
            if any(ex == exchange and sym == symbol.upper() for ex, sym, _ in company.listings):
                return company
        raise ProviderNotFoundError(f"demo has no {exchange} listing {symbol}")

    @staticmethod
    def close_price(company: _DemoCompany, exchange: Exchange, day: date) -> Decimal:
        t = (day - FIRST_DATE).days
        trend = 1 + 0.0002 * t
        cycle = 1 + 0.12 * math.sin(t / 45)
        jitter = 1 + 0.01 * _noise(company.key, day.isoformat())
        venue = 1 + (0.001 if exchange == "BSE" else 0.0)  # BSE trades a hair away from NSE
        return _tick(company.base_price * trend * cycle * jitter * venue)

    # --- MarketDataProvider ----------------------------------------------------------------------

    def status(self) -> ProviderStatus:
        return ProviderStatus(NAME, True, self._as_of(), self._retrieved_at(), detail="synthetic")

    def fetch_directory(self) -> DirectoryResult:
        as_of = self._as_of()
        listings = [
            InstrumentListing(
                exchange=exchange,
                symbol=symbol,
                name=company.name,
                isin=None,
                series=series,
                company_key=company.key,
                currency="INR",
                provider_instrument_key=f"demo:{exchange}:{symbol}",
                last_traded_on=as_of,
            )
            for company in COMPANIES
            for exchange, symbol, series in company.listings
        ]
        return DirectoryResult(NAME, listings, as_of, self._retrieved_at(), [])

    def fetch_eod_bars(
        self, exchange: Exchange, symbol: str, start: date, end: date
    ) -> PriceSeries:
        company = self._find(exchange, symbol)
        end = min(end, self._as_of())
        bars: list[PriceBar] = []
        day = max(start, FIRST_DATE)
        while day <= end:
            if day.weekday() < 5:
                close = self.close_price(company, exchange, day)
                prev = self.close_price(company, exchange, _previous_weekday(day - timedelta(1)))
                spread = abs(_noise("range", company.key, day.isoformat())) * 0.015 + 0.002
                high = max(close, prev) * Decimal(str(1 + spread))
                low = min(close, prev) * Decimal(str(1 - spread))
                volume = int(1_000_000 * (1.5 + _noise("vol", company.key, day.isoformat())))
                bars.append(
                    PriceBar(
                        date=day,
                        open=prev,
                        high=_tick(float(high)),
                        low=_tick(float(low)),
                        close=close,
                        volume=volume,
                        prev_close=prev,
                    )
                )
            day += timedelta(days=1)
        return PriceSeries(
            provider=NAME,
            exchange=exchange,
            symbol=symbol.upper(),
            currency="INR",
            nature="demo",
            adjusted=False,
            bars=bars,
            retrieved_at=self._retrieved_at(),
            source_url=None,
        )

    def fetch_corporate_actions(self, symbol: str) -> CorporateActionsResult:
        fy_end = _latest_completed_fy_end(self._today())
        actions: list[CorporateAction] = []
        for company in COMPANIES:
            for exchange, listed_symbol, _ in company.listings:
                if listed_symbol != symbol.upper():
                    continue
                if company.key == "demo:1":
                    for years_back in range(3):
                        ex_date = date(fy_end.year - years_back, 7, 15)
                        if ex_date <= self._today():
                            actions.append(
                                _action(exchange, listed_symbol, ex_date, "dividend", cash="18")
                            )
                elif company.key == "demo:2":
                    actions.append(
                        _action(exchange, listed_symbol, date(2022, 9, 1), "split", ratio=(2, 1))
                    )
                elif company.key == "demo:4":
                    ex_date = fy_end + timedelta(days=45)
                    if ex_date <= self._today():
                        actions.append(
                            _action(exchange, listed_symbol, ex_date, "bonus", ratio=(1, 1))
                        )
        actions.sort(key=lambda a: (a.ex_date, a.exchange), reverse=True)
        return CorporateActionsResult(NAME, actions, self._retrieved_at(), None)

    # --- FundamentalsProvider --------------------------------------------------------------------

    def fetch_financials(self, ref: InstrumentRef) -> IngestionResult:
        company = self._find(ref.exchange, ref.symbol)
        fy_end = _latest_completed_fy_end(self._today())
        warnings: list[str] = ["synthetic demo data - not real financial statements"]
        periods: list[IngestedPeriod] = []
        for basis in company.bases:
            factor = Decimal("0.7") if basis == "standalone" and len(company.bases) > 1 else 1
            for years_back in range(5):
                fiscal_year = fy_end.year - years_back
                revenue = company.revenue_cr * factor / (1 + company.growth) ** years_back
                loss = company.loss_latest_year and years_back == 0
                periods.append(
                    _period(
                        company,
                        basis,
                        fiscal_year,
                        "FY",
                        fy_end.replace(fiscal_year),
                        revenue,
                        loss,
                        warnings,
                    )
                )
            for q in range(4):
                # Quarters of the current fiscal year that have ended, newest first.
                q_end = _quarter_end(fy_end, q + 1)
                if q_end + timedelta(days=45) > self._today():
                    continue
                revenue = company.revenue_cr * factor * (1 + company.growth) / 4
                periods.append(
                    _period(
                        company,
                        basis,
                        fy_end.year + 1,
                        f"Q{q + 1}",
                        q_end,
                        revenue,
                        False,
                        warnings,
                        quarterly=True,
                    )
                )
        return IngestionResult(
            provider=NAME,
            source_url="demo://synthetic",
            retrieved_at=self._retrieved_at(),
            entity_name=company.name,
            periods=periods,
            warnings=warnings,
        )


def _action(
    exchange: Exchange,
    symbol: str,
    ex_date: date,
    kind: str,
    *,
    cash: str | None = None,
    ratio: tuple[int, int] | None = None,
) -> CorporateAction:
    return CorporateAction(
        exchange=exchange,
        symbol=symbol,
        isin=None,
        ex_date=ex_date,
        record_date=ex_date,
        action_type=kind,  # type: ignore[arg-type]
        ratio_numerator=ratio[0] if ratio else None,
        ratio_denominator=ratio[1] if ratio else None,
        cash_amount=Decimal(cash) if cash else None,
        face_value_from=None,
        face_value_to=None,
        description=f"[DEMO] {kind}" + (f" Rs {cash} per share" if cash else ""),
    )


def _quarter_end(fy_end: date, quarter: int) -> date:
    """End of fiscal quarter ``quarter`` of the fiscal year that starts the day after fy_end."""
    if quarter == 4:
        return date(fy_end.year + 1, 3, 31)
    month = 3 + 3 * quarter
    return date(fy_end.year, month, {6: 30, 9: 30, 12: 31}[month])


def _r(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), ROUND_HALF_UP)


def _period(
    company: _DemoCompany,
    basis: str,
    fiscal_year: int,
    fiscal_period: str,
    period_end: date,
    revenue: Decimal,
    loss: bool,
    warnings: list[str],
    *,
    quarterly: bool = False,
) -> IngestedPeriod:
    """Synthetic statements in ₹ crore; internally consistent so ratios are computable."""
    margin = Decimal("-0.02") if loss else company.net_margin
    cost = revenue * Decimal("0.6")
    d_and_a = revenue * Decimal("0.04")
    interest = revenue * Decimal("0.015")
    operating_income = revenue * (margin + Decimal("0.10"))
    pretax = operating_income - interest
    net_income = revenue * margin
    tax = pretax - net_income
    # Balance sheets are stocks, not flows: size them off annualized revenue.
    total_assets = revenue * (4 if quarterly else 1) * Decimal("1.4")
    equity = total_assets * Decimal("0.5")
    debt = total_assets * Decimal("0.2")
    eps = net_income * Decimal(10) ** 7 / company.shares
    income = {
        "revenue": revenue,
        "cost_of_revenue": cost,
        "gross_profit": revenue - cost,
        "operating_income": operating_income,
        "depreciation_amortization": d_and_a,
        "interest_expense": interest,
        "pretax_income": pretax,
        "income_tax_expense": tax,
        "net_income": net_income,
        "diluted_shares": Decimal(company.shares),
        "diluted_eps": eps,
    }
    balance = {
        "cash_and_equivalents": total_assets * Decimal("0.08"),
        "total_current_assets": total_assets * Decimal("0.35"),
        "total_assets": total_assets,
        "total_current_liabilities": total_assets * Decimal("0.2"),
        "short_term_debt": debt * Decimal("0.25"),
        "long_term_debt": debt * Decimal("0.75"),
        "total_liabilities": total_assets - equity,
        "total_equity": equity,
        "shares_outstanding": Decimal(company.shares),
    }
    cash_flow = {
        "operating_cash_flow": net_income + d_and_a + revenue * Decimal("0.02"),
        "capital_expenditures": revenue * Decimal("0.05"),
        "dividends_paid": max(net_income * Decimal("0.3"), Decimal(0)),
    }
    label = f"{fiscal_period} FY{fiscal_year}" if quarterly else f"FY{fiscal_year}"
    items: list[IngestedLineItem] = []
    for statement, values in (("income", income), ("balance", balance), ("cash_flow", cash_flow)):
        statement_items = [
            IngestedLineItem(
                statement=statement,  # type: ignore[arg-type]
                item=item,
                value=value if item in ("diluted_shares", "shares_outstanding") else _r(value),
                source_concept=f"demo:{item}",
                source_accession=None,
            )
            for item, value in values.items()
        ]
        items.extend(
            validate_statement_items(statement, statement_items, label, warnings)  # type: ignore[arg-type]
        )
    return IngestedPeriod(
        fiscal_year=fiscal_year,
        fiscal_period=fiscal_period,
        period_start=None,
        period_end=period_end,
        currency="INR",
        scale="crores",
        items=items,
        basis=basis,  # type: ignore[arg-type]
    )
