from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest

from app.domain.market_multiples import MarketPrice, compute_market_multiples
from app.domain.statements import BalanceSheet, FinancialPeriodData, IncomeStatement
from app.domain.types import FiscalPeriod, ReportingPeriod, Scale, SourceRef
from tests.domain.helpers import D, approx

SOURCE = SourceRef(provider="unit-test", retrieved_at=datetime(2026, 6, 1, tzinfo=UTC))
INCOME = {
    "revenue": D(1000),
    "operating_income": D(200),
    "depreciation_amortization": D(50),
    "net_income": D(150),
    "diluted_eps": D(15),  # rupees per share (unscaled)
}
BALANCE = {
    "cash_and_equivalents": D(100),
    "total_debt": D(300),
    "minority_interest": D(20),
    "total_equity": D(750),
    "shares_outstanding": D(100_000_000),  # 10 crore shares (unscaled)
}


def data(
    *,
    income: dict[str, Any] | None = None,
    balance: dict[str, Any] | None = None,
    fiscal_period: FiscalPeriod = FiscalPeriod.FY,
) -> FinancialPeriodData:
    return FinancialPeriodData(
        company="DEMOCO",
        period=ReportingPeriod(
            fiscal_year=2026, fiscal_period=fiscal_period, period_end=date(2026, 3, 31)
        ),
        currency="INR",
        scale=Scale.CRORES,  # statement amounts in ₹ crore
        source=SOURCE,
        income=IncomeStatement(**(INCOME if income is None else income)),
        balance=BalanceSheet(**(BALANCE if balance is None else balance)),
    )


PRICE = MarketPrice(price=D(300), price_date=date(2026, 10, 16), currency="INR", source="test")


def test_multiples_in_crores_are_exact() -> None:
    m = compute_market_multiples(data(), PRICE, trailing_dividends_per_share=D(6)).metrics
    # 300 * 10 crore shares = ₹3000 crore
    assert m["market_cap"].value == D(3000)
    # EV = 3000 + 300 debt + 20 minority - 100 cash; preferred not reported -> noted, not added
    assert m["enterprise_value"].value == D(3220)
    assert m["enterprise_value"].note == "not reported, so not added: preferred_equity"
    assert m["price_to_earnings"].value == D(20)
    assert m["price_to_book"].value == D(4)
    assert approx(m["ev_to_ebitda"].value, D(3220) / D(250))
    assert approx(m["ev_to_revenue"].value, "3.22")
    assert m["dividend_yield"].value == D("0.02")
    assert {r.kind.value for r in m.values()} == {"calculated"}


def test_losses_and_negative_ebitda_are_not_meaningful() -> None:
    loss = {**INCOME, "net_income": D(-10), "diluted_eps": D(-1), "operating_income": D(-80)}
    m = compute_market_multiples(data(income=loss), PRICE).metrics
    assert m["price_to_earnings"].status == "not_meaningful"
    assert m["ev_to_ebitda"].status == "not_meaningful"  # EBITDA = -80 + 50 < 0
    assert m["price_to_earnings"].value is None


def test_missing_debt_or_cash_is_never_zero_filled() -> None:
    no_cash = {k: v for k, v in BALANCE.items() if k != "cash_and_equivalents"}
    m = compute_market_multiples(data(balance=no_cash), PRICE).metrics
    assert m["market_cap"].status == "ok"
    assert m["enterprise_value"].status == "missing_inputs"
    assert m["enterprise_value"].missing == ["cash_and_equivalents"]
    assert m["ev_to_ebitda"].status == "missing_inputs"
    assert m["dividend_yield"].status == "missing_inputs"  # no dividend data supplied


def test_share_count_change_after_period_blocks_per_share_metrics() -> None:
    report = compute_market_multiples(
        data(), PRICE, share_count_events_after_period=["bonus ex 2026-05-15"]
    )
    for name in ("market_cap", "enterprise_value", "price_to_earnings", "price_to_book"):
        assert report.metrics[name].status == "not_meaningful"
        assert report.metrics[name].value is None
    assert [i.code for i in report.issues] == ["share_count_changed_after_period"]


def test_stale_and_quarterly_fundamentals_are_flagged() -> None:
    late = PRICE.model_copy(update={"price_date": date(2027, 9, 1)})
    codes = {i.code for i in compute_market_multiples(data(), late).issues}
    assert codes == {"stale_fundamentals"}
    quarterly = compute_market_multiples(data(fiscal_period=FiscalPeriod.Q1), PRICE)
    assert {i.code for i in quarterly.issues} == {"non_annual_period"}


def test_inputs_are_validated() -> None:
    with pytest.raises(ValueError, match="currency"):
        compute_market_multiples(data(), PRICE.model_copy(update={"currency": "USD"}))
    with pytest.raises(ValueError, match="price date"):
        compute_market_multiples(data(), PRICE.model_copy(update={"price_date": date(2026, 1, 1)}))
    with pytest.raises(ValueError):
        MarketPrice(price=Decimal(0), price_date=date(2026, 1, 1), currency="INR", source="x")
