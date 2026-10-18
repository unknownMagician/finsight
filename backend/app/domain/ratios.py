"""Financial ratios and derived metrics from normalized statements.

Each metric returns a ``MetricResult`` with the formula, the exact inputs used, and a status:
- ``ok``: computed.
- ``missing_inputs``: at least one input was not reported (``missing`` lists which).
- ``not_meaningful``: inputs exist but the ratio has no economic meaning (e.g. a zero or
  negative denominator such as negative equity for ROE).

Ratios are fractions (0.25 == 25%); ``times`` are multiples; ``currency`` amounts are in the
statement's currency and scale.
"""

from decimal import Decimal
from typing import Literal

from pydantic import Field

from app.domain.statements import FinancialPeriodData
from app.domain.types import (
    CurrencyCode,
    DomainModel,
    ReportingBasis,
    ReportingPeriod,
    Scale,
    ValueKind,
    rescale,
)

MetricUnit = Literal["ratio", "times", "currency"]
MetricStatus = Literal["ok", "missing_inputs", "not_meaningful"]


class MetricResult(DomainModel):
    name: str
    value: Decimal | None
    unit: MetricUnit
    kind: ValueKind = ValueKind.CALCULATED
    formula: str
    inputs: dict[str, Decimal | None]
    status: MetricStatus
    missing: list[str] = Field(default_factory=list)
    note: str | None = None


class RatioReport(DomainModel):
    company: str
    period: ReportingPeriod
    currency: CurrencyCode
    scale: Scale
    basis: ReportingBasis = "unspecified"
    metrics: dict[str, MetricResult]


def _missing(inputs: dict[str, Decimal | None]) -> list[str]:
    return [name for name, value in inputs.items() if value is None]


def _amount(
    name: str, formula: str, inputs: dict[str, Decimal | None], compute: Decimal | None
) -> MetricResult:
    missing = _missing(inputs)
    if missing:
        return MetricResult(
            name=name,
            value=None,
            unit="currency",
            formula=formula,
            inputs=inputs,
            status="missing_inputs",
            missing=missing,
        )
    return MetricResult(
        name=name, value=compute, unit="currency", formula=formula, inputs=inputs, status="ok"
    )


def _divide(
    name: str,
    formula: str,
    unit: MetricUnit,
    numerator: tuple[str, Decimal | None],
    denominator: tuple[str, Decimal | None],
    *,
    extra_inputs: dict[str, Decimal | None] | None = None,
    note: str | None = None,
) -> MetricResult:
    """numerator / denominator, requiring a strictly positive denominator."""
    inputs = {**(extra_inputs or {}), numerator[0]: numerator[1], denominator[0]: denominator[1]}
    missing = _missing(inputs)
    if missing:
        return MetricResult(
            name=name,
            value=None,
            unit=unit,
            formula=formula,
            inputs=inputs,
            status="missing_inputs",
            missing=missing,
            note=note,
        )
    num, den = numerator[1], denominator[1]
    assert num is not None and den is not None  # noqa: S101 - narrowed by _missing above
    if den <= 0:
        return MetricResult(
            name=name,
            value=None,
            unit=unit,
            formula=formula,
            inputs=inputs,
            status="not_meaningful",
            note=f"{denominator[0]} must be positive (got {den})",
        )
    return MetricResult(
        name=name,
        value=num / den,
        unit=unit,
        formula=formula,
        inputs=inputs,
        status="ok",
        note=note,
    )


def _sum_if_all(*values: Decimal | None) -> Decimal | None:
    if any(v is None for v in values):
        return None
    return sum((v for v in values if v is not None), Decimal(0))


def _average(
    current: Decimal | None, prior: Decimal | None, has_prior: bool
) -> tuple[Decimal | None, str]:
    if not has_prior:
        return current, "ending balance (no prior period supplied)"
    if current is None or prior is None:
        return None, "average of opening and closing balance"
    return (current + prior) / 2, "average of opening and closing balance"


def gross_profit(data: FinancialPeriodData) -> tuple[Decimal | None, str]:
    """Reported gross profit, else revenue - cost_of_revenue."""
    inc = data.income
    if inc.gross_profit is not None:
        return inc.gross_profit, "reported"
    if inc.revenue is not None and inc.cost_of_revenue is not None:
        return inc.revenue - inc.cost_of_revenue, "revenue - cost_of_revenue"
    return None, "unavailable"


def total_debt(data: FinancialPeriodData) -> Decimal | None:
    """Reported total debt, else short_term_debt + long_term_debt (both required)."""
    bal = data.balance
    if bal.total_debt is not None:
        return bal.total_debt
    return _sum_if_all(bal.short_term_debt, bal.long_term_debt)


def ebitda(data: FinancialPeriodData) -> Decimal | None:
    """EBIT + depreciation & amortization."""
    return _sum_if_all(data.income.operating_income, data.income.depreciation_amortization)


def compute_ratios(
    data: FinancialPeriodData, prior: FinancialPeriodData | None = None
) -> RatioReport:
    """Compute all supported metrics for ``data``.

    ``prior`` (the preceding period) enables growth rates and average-balance returns. It must
    be the same company and currency; its amounts are rescaled to ``data.scale``.
    """
    if prior is not None:
        if prior.company != data.company:
            raise ValueError("prior period belongs to a different company")
        if prior.currency != data.currency:
            raise ValueError("prior period currency differs; convert currencies before comparing")
        if prior.basis != data.basis:
            raise ValueError("prior period reporting basis differs (consolidated vs standalone)")
        if prior.period.period_end >= data.period.period_end:
            raise ValueError("prior period must end before the current period")

    def p(value: Decimal | None) -> Decimal | None:
        if prior is None or value is None:
            return None
        return rescale(value, prior.scale, data.scale)

    inc, bal, cf = data.income, data.balance, data.cash_flow
    has_prior = prior is not None
    gp, gp_note = gross_profit(data)
    debt = total_debt(data)
    ebitda_value = ebitda(data)

    avg_equity, avg_equity_note = _average(
        bal.total_equity, p(prior.balance.total_equity) if prior else None, has_prior
    )
    avg_assets, avg_assets_note = _average(
        bal.total_assets, p(prior.balance.total_assets) if prior else None, has_prior
    )

    m: dict[str, MetricResult] = {}

    m["gross_margin"] = _divide(
        "Gross margin",
        "gross_profit / revenue",
        "ratio",
        ("gross_profit", gp),
        ("revenue", inc.revenue),
        note=f"gross_profit: {gp_note}",
    )
    m["operating_margin"] = _divide(
        "Operating margin",
        "operating_income / revenue",
        "ratio",
        ("operating_income", inc.operating_income),
        ("revenue", inc.revenue),
    )
    m["ebitda"] = _amount(
        "EBITDA",
        "operating_income + depreciation_amortization",
        {
            "operating_income": inc.operating_income,
            "depreciation_amortization": inc.depreciation_amortization,
        },
        ebitda_value,
    )
    m["ebitda_margin"] = _divide(
        "EBITDA margin",
        "ebitda / revenue",
        "ratio",
        ("ebitda", ebitda_value),
        ("revenue", inc.revenue),
    )
    m["net_margin"] = _divide(
        "Net margin",
        "net_income / revenue",
        "ratio",
        ("net_income", inc.net_income),
        ("revenue", inc.revenue),
    )
    m["effective_tax_rate"] = _divide(
        "Effective tax rate",
        "income_tax_expense / pretax_income",
        "ratio",
        ("income_tax_expense", inc.income_tax_expense),
        ("pretax_income", inc.pretax_income),
    )
    m["return_on_equity"] = _divide(
        "Return on equity",
        "net_income / total_equity",
        "ratio",
        ("net_income", inc.net_income),
        ("total_equity", avg_equity),
        note=f"total_equity: {avg_equity_note}",
    )
    m["return_on_assets"] = _divide(
        "Return on assets",
        "net_income / total_assets",
        "ratio",
        ("net_income", inc.net_income),
        ("total_assets", avg_assets),
        note=f"total_assets: {avg_assets_note}",
    )
    capital_employed = (
        bal.total_assets - bal.total_current_liabilities
        if bal.total_assets is not None and bal.total_current_liabilities is not None
        else None
    )
    m["return_on_capital_employed"] = _divide(
        "Return on capital employed",
        "operating_income / (total_assets - total_current_liabilities)",
        "ratio",
        ("operating_income", inc.operating_income),
        ("capital_employed", capital_employed),
        extra_inputs={
            "total_assets": bal.total_assets,
            "total_current_liabilities": bal.total_current_liabilities,
        },
        note="capital_employed: ending balance; operating_income is pre-tax EBIT",
    )
    m["asset_turnover"] = _divide(
        "Asset turnover",
        "revenue / total_assets",
        "times",
        ("revenue", inc.revenue),
        ("total_assets", avg_assets),
        note=f"total_assets: {avg_assets_note}",
    )
    m["current_ratio"] = _divide(
        "Current ratio",
        "total_current_assets / total_current_liabilities",
        "times",
        ("total_current_assets", bal.total_current_assets),
        ("total_current_liabilities", bal.total_current_liabilities),
    )
    quick_assets = (
        bal.total_current_assets - bal.inventory
        if bal.total_current_assets is not None and bal.inventory is not None
        else None
    )
    m["quick_ratio"] = _divide(
        "Quick ratio",
        "(total_current_assets - inventory) / total_current_liabilities",
        "times",
        ("quick_assets", quick_assets),
        ("total_current_liabilities", bal.total_current_liabilities),
        extra_inputs={"total_current_assets": bal.total_current_assets, "inventory": bal.inventory},
    )
    m["total_debt"] = _amount(
        "Total debt",
        "total_debt (reported) or short_term_debt + long_term_debt",
        {"total_debt": debt},
        debt,
    )
    m["debt_to_equity"] = _divide(
        "Debt to equity",
        "total_debt / total_equity",
        "times",
        ("total_debt", debt),
        ("total_equity", bal.total_equity),
    )
    net_debt_value = (
        debt - bal.cash_and_equivalents
        if debt is not None and bal.cash_and_equivalents is not None
        else None
    )
    m["net_debt"] = _amount(
        "Net debt",
        "total_debt - cash_and_equivalents",
        {"total_debt": debt, "cash_and_equivalents": bal.cash_and_equivalents},
        net_debt_value,
    )
    m["net_debt_to_ebitda"] = _divide(
        "Net debt to EBITDA",
        "net_debt / ebitda",
        "times",
        ("net_debt", net_debt_value),
        ("ebitda", ebitda_value),
    )
    m["interest_coverage"] = _divide(
        "Interest coverage",
        "operating_income / interest_expense",
        "times",
        ("operating_income", inc.operating_income),
        ("interest_expense", inc.interest_expense),
    )
    fcf = (
        cf.operating_cash_flow - cf.capital_expenditures
        if cf.operating_cash_flow is not None and cf.capital_expenditures is not None
        else None
    )
    m["free_cash_flow"] = _amount(
        "Free cash flow",
        "operating_cash_flow - capital_expenditures",
        {
            "operating_cash_flow": cf.operating_cash_flow,
            "capital_expenditures": cf.capital_expenditures,
        },
        fcf,
    )
    m["fcf_margin"] = _divide(
        "FCF margin",
        "free_cash_flow / revenue",
        "ratio",
        ("free_cash_flow", fcf),
        ("revenue", inc.revenue),
    )

    if prior is not None:
        prior_revenue = p(prior.income.revenue)
        growth = _divide(
            "Revenue growth",
            "revenue / prior_revenue - 1",
            "ratio",
            ("revenue", inc.revenue),
            ("prior_revenue", prior_revenue),
        )
        if growth.value is not None:
            growth = growth.model_copy(update={"value": growth.value - 1})
        m["revenue_growth"] = growth
        earnings_growth = _divide(
            "Net income growth",
            "net_income / prior_net_income - 1",
            "ratio",
            ("net_income", inc.net_income),
            ("prior_net_income", p(prior.income.net_income)),
            note="not meaningful when prior net income is zero or negative",
        )
        if earnings_growth.value is not None:
            earnings_growth = earnings_growth.model_copy(
                update={"value": earnings_growth.value - 1}
            )
        m["net_income_growth"] = earnings_growth

    return RatioReport(
        company=data.company,
        period=data.period,
        currency=data.currency,
        scale=data.scale,
        basis=data.basis,
        metrics=m,
    )
