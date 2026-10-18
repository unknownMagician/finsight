from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest

from app.domain.ratios import compute_ratios
from app.domain.statements import (
    BalanceSheet,
    CashFlowStatement,
    FinancialPeriodData,
    IncomeStatement,
)
from app.domain.types import ReportingPeriod, Scale, SourceRef
from tests.domain.helpers import D, approx

SOURCE = SourceRef(provider="unit-test", retrieved_at=datetime(2026, 1, 1, tzinfo=UTC))


def period_data(
    year: int = 2025,
    *,
    scale: Scale = Scale.MILLIONS,
    currency: str = "USD",
    income: dict[str, Any] | None = None,
    balance: dict[str, Any] | None = None,
    cash_flow: dict[str, Any] | None = None,
) -> FinancialPeriodData:
    return FinancialPeriodData(
        company="ACME",
        period=ReportingPeriod(fiscal_year=year, period_end=date(year, 12, 31)),
        currency=currency,
        scale=scale,
        source=SOURCE,
        income=IncomeStatement(**(income or {})),
        balance=BalanceSheet(**(balance or {})),
        cash_flow=CashFlowStatement(**(cash_flow or {})),
    )


FULL_INCOME = {
    "revenue": D(1000),
    "cost_of_revenue": D(600),
    "operating_income": D(200),
    "depreciation_amortization": D(50),
    "interest_expense": D(20),
    "pretax_income": D(180),
    "income_tax_expense": D(45),
    "net_income": D(135),
}
FULL_BALANCE = {
    "cash_and_equivalents": D(100),
    "inventory": D(100),
    "total_current_assets": D(500),
    "total_current_liabilities": D(250),
    "short_term_debt": D(50),
    "long_term_debt": D(350),
    "total_assets": D(2000),
    "total_equity": D(900),
}
FULL_CASH_FLOW = {"operating_cash_flow": D(250), "capital_expenditures": D(80)}


@pytest.fixture
def current() -> FinancialPeriodData:
    return period_data(income=FULL_INCOME, balance=FULL_BALANCE, cash_flow=FULL_CASH_FLOW)


EXPECTED_SINGLE_PERIOD: dict[str, Decimal] = {
    "gross_margin": D("0.4"),
    "operating_margin": D("0.2"),
    "ebitda": D(250),
    "ebitda_margin": D("0.25"),
    "net_margin": D("0.135"),
    "effective_tax_rate": D("0.25"),
    "return_on_equity": D("0.15"),
    "return_on_assets": D("0.0675"),
    "asset_turnover": D("0.5"),
    "current_ratio": D(2),
    "quick_ratio": D("1.6"),
    "total_debt": D(400),
    "debt_to_equity": D(400) / D(900),
    "net_debt": D(300),
    "net_debt_to_ebitda": D("1.2"),
    "interest_coverage": D(10),
    "free_cash_flow": D(170),
    "fcf_margin": D("0.17"),
    "return_on_capital_employed": D(200) / D(1750),  # EBIT / (assets - current liabilities)
}


@pytest.mark.parametrize(("metric", "expected"), EXPECTED_SINGLE_PERIOD.items())
def test_single_period_metrics(
    current: FinancialPeriodData, metric: str, expected: Decimal
) -> None:
    result = compute_ratios(current).metrics[metric]
    assert result.status == "ok", result
    assert approx(result.value, expected)


def test_gross_profit_derivation_is_recorded(current: FinancialPeriodData) -> None:
    gm = compute_ratios(current).metrics["gross_margin"]
    assert gm.note == "gross_profit: revenue - cost_of_revenue"
    assert gm.inputs == {"gross_profit": D(400), "revenue": D(1000)}


def test_reported_gross_profit_takes_precedence() -> None:
    data = period_data(income={**FULL_INCOME, "gross_profit": D(450)})
    gm = compute_ratios(data).metrics["gross_margin"]
    assert approx(gm.value, "0.45")
    assert gm.note == "gross_profit: reported"


def test_without_prior_uses_ending_balances_and_omits_growth(current: FinancialPeriodData) -> None:
    report = compute_ratios(current)
    assert "revenue_growth" not in report.metrics
    assert "ending balance" in (report.metrics["return_on_equity"].note or "")


def test_prior_period_in_different_scale_is_rescaled(current: FinancialPeriodData) -> None:
    prior = period_data(
        2024,
        scale=Scale.THOUSANDS,
        income={"revenue": D(800_000)},
        balance={"total_equity": D(700_000), "total_assets": D(1_800_000)},
    )
    m = compute_ratios(current, prior).metrics
    assert approx(m["revenue_growth"].value, "0.25")
    assert approx(m["return_on_equity"].value, D(135) / D(800))
    assert approx(m["return_on_assets"].value, D(135) / D(1900))
    assert "average" in (m["return_on_equity"].note or "")


def test_missing_inputs_are_reported_not_zero_filled() -> None:
    data = period_data(income={"revenue": D(1000)}, balance={"total_current_assets": D(500)})
    m = compute_ratios(data).metrics
    assert m["net_margin"].status == "missing_inputs"
    assert m["net_margin"].value is None
    assert m["net_margin"].missing == ["net_income"]
    assert m["quick_ratio"].status == "missing_inputs"
    assert "inventory" in m["quick_ratio"].missing


def test_total_debt_requires_both_components_unless_reported() -> None:
    only_long_term = period_data(balance={"long_term_debt": D(350)})
    assert compute_ratios(only_long_term).metrics["total_debt"].status == "missing_inputs"
    reported = period_data(balance={"long_term_debt": D(350), "total_debt": D(375)})
    assert compute_ratios(reported).metrics["total_debt"].value == D(375)


@pytest.mark.parametrize(
    ("overrides", "metric"),
    [
        ({"balance": {**FULL_BALANCE, "total_equity": D(-50)}}, "return_on_equity"),
        ({"balance": {**FULL_BALANCE, "total_equity": D(-50)}}, "debt_to_equity"),
        ({"income": {**FULL_INCOME, "revenue": D(0)}}, "net_margin"),
        ({"income": {**FULL_INCOME, "interest_expense": D(0)}}, "interest_coverage"),
        ({"income": {**FULL_INCOME, "pretax_income": D(-10)}}, "effective_tax_rate"),
    ],
)
def test_non_positive_denominators_are_not_meaningful(
    overrides: dict[str, Any], metric: str
) -> None:
    kwargs: dict[str, Any] = {
        "income": FULL_INCOME,
        "balance": FULL_BALANCE,
        "cash_flow": FULL_CASH_FLOW,
    } | overrides
    result = compute_ratios(period_data(**kwargs)).metrics[metric]
    assert result.status == "not_meaningful"
    assert result.value is None
    assert result.note


def test_negative_numerator_is_allowed(current: FinancialPeriodData) -> None:
    loss = period_data(income={**FULL_INCOME, "net_income": D(-100)}, balance=FULL_BALANCE)
    assert approx(compute_ratios(loss).metrics["net_margin"].value, "-0.1")


def test_prior_validation(current: FinancialPeriodData) -> None:
    with pytest.raises(ValueError, match="currency"):
        compute_ratios(current, period_data(2024, currency="EUR"))
    with pytest.raises(ValueError, match="end before"):
        compute_ratios(current, period_data(2026))


def test_all_metrics_are_labelled_calculated(current: FinancialPeriodData) -> None:
    assert {m.kind.value for m in compute_ratios(current).metrics.values()} == {"calculated"}


def test_net_income_growth_and_its_edge_cases(current: FinancialPeriodData) -> None:
    prior = period_data(2024, income={**FULL_INCOME, "net_income": D(108)}, balance=FULL_BALANCE)
    growth = compute_ratios(current, prior).metrics["net_income_growth"]
    assert growth.status == "ok" and approx(growth.value, D(135) / D(108) - 1)

    prior_loss = period_data(2024, income={**FULL_INCOME, "net_income": D(-50)})
    turnaround = compute_ratios(current, prior_loss).metrics["net_income_growth"]
    assert turnaround.status == "not_meaningful" and turnaround.value is None


def test_capital_employed_needs_both_inputs() -> None:
    data = period_data(income=FULL_INCOME, balance={"total_assets": D(2000)})
    roce = compute_ratios(data).metrics["return_on_capital_employed"]
    assert roce.status == "missing_inputs" and "total_current_liabilities" in roce.missing


def test_consolidated_and_standalone_are_never_mixed(current: FinancialPeriodData) -> None:
    consolidated = current.model_copy(update={"basis": "consolidated"})
    standalone = period_data(2024, income=FULL_INCOME).model_copy(update={"basis": "standalone"})
    with pytest.raises(ValueError, match="basis"):
        compute_ratios(consolidated, standalone)
    report = compute_ratios(consolidated, standalone.model_copy(update={"basis": "consolidated"}))
    assert report.basis == "consolidated"
