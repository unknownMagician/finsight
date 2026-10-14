"""Weighted average cost of capital.

    cost_of_equity          = risk_free_rate + beta * equity_risk_premium + size_premium   (CAPM)
    after_tax_cost_of_debt  = pre_tax_cost_of_debt * (1 - tax_rate)
    E/V, D/V                = equity_value / (equity_value + debt_value), debt_value / (...)
    wacc                    = E/V * cost_of_equity + D/V * after_tax_cost_of_debt

Weights should use market values; that is the caller's responsibility.
"""

from decimal import Decimal

from pydantic import Field

from app.domain.types import Amount, DomainModel, Issue, Rate


class WACCInputs(DomainModel):
    risk_free_rate: Rate = Field(ge=Decimal("-0.05"), le=Decimal("0.25"))
    equity_risk_premium: Rate = Field(ge=0, le=Decimal("0.25"))
    beta: Decimal = Field(ge=-2, le=5, allow_inf_nan=False)
    size_premium: Rate = Field(default=Decimal(0), ge=0, le=Decimal("0.15"))
    pre_tax_cost_of_debt: Rate = Field(ge=0, le=Decimal("0.5"))
    tax_rate: Rate = Field(ge=0, lt=1)
    equity_value: Amount = Field(gt=0)
    debt_value: Amount = Field(ge=0)


class WACCResult(DomainModel):
    cost_of_equity: Decimal
    after_tax_cost_of_debt: Decimal
    equity_weight: Decimal
    debt_weight: Decimal
    wacc: Decimal
    warnings: list[Issue]


def compute_wacc(inputs: WACCInputs) -> WACCResult:
    cost_of_equity = (
        inputs.risk_free_rate + inputs.beta * inputs.equity_risk_premium + inputs.size_premium
    )
    after_tax_kd = inputs.pre_tax_cost_of_debt * (1 - inputs.tax_rate)
    total = inputs.equity_value + inputs.debt_value
    we = inputs.equity_value / total
    wd = inputs.debt_value / total
    wacc = we * cost_of_equity + wd * after_tax_kd

    if wacc <= 0:
        raise ValueError(f"computed WACC must be positive (got {wacc}); check inputs")

    warnings: list[Issue] = []
    if inputs.debt_value > 0 and cost_of_equity < after_tax_kd:
        warnings.append(
            Issue(
                code="equity_cheaper_than_debt",
                message="Cost of equity is below after-tax cost of debt, which is unusual.",
            )
        )
    if not Decimal("0.04") <= wacc <= Decimal("0.20"):
        warnings.append(
            Issue(code="unusual_wacc", message=f"WACC {wacc:.4f} is outside the usual 4%-20% band.")
        )
    return WACCResult(
        cost_of_equity=cost_of_equity,
        after_tax_cost_of_debt=after_tax_kd,
        equity_weight=we,
        debt_weight=wd,
        wacc=wacc,
        warnings=warnings,
    )
