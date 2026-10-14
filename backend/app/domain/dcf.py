"""Discounted cash flow valuation (unlevered free cash flow to the firm) and sensitivity.

For explicit years t = 1..N with free cash flows FCF_t:

    discount_period_t = t            (end-of-year)   or   t - 0.5   (mid-year convention)
    discount_factor_t = 1 / (1 + wacc) ** discount_period_t
    PV_t              = FCF_t * discount_factor_t

Terminal value at the end of year N:

    perpetuity growth: TV = FCF_N * (1 + g) / (wacc - g)          requires g < wacc
    exit multiple:     TV = terminal_ebitda * exit_multiple        (EV / EBITDA)

    PV(TV)            = TV / (1 + wacc) ** N     (always end-of-year N, also under mid-year)

    enterprise_value  = sum(PV_t) + PV(TV)
    equity_value      = enterprise_value - net_debt - other_claims
    value_per_share   = equity_value / shares_outstanding         (None if equity_value <= 0)

Cross-checks:
    implied exit multiple (perpetuity method, if terminal_ebitda given) = TV / terminal_ebitda
    implied perpetual growth (exit method) g = (TV * wacc - FCF_N) / (TV + FCF_N)
"""

from collections.abc import Sequence
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, ValidationError, model_validator

from app.domain.types import Amount, CurrencyCode, DomainModel, Issue, IssueSeverity, Rate, Scale

MAX_PROJECTION_YEARS = 30
MAX_SENSITIVITY_AXIS = 15


class TerminalMethod(StrEnum):
    PERPETUITY_GROWTH = "perpetuity_growth"
    EXIT_MULTIPLE = "exit_multiple"


class DCFInputs(DomainModel):
    currency: CurrencyCode
    scale: Scale
    free_cash_flows: Annotated[list[Amount], Field(min_length=1, max_length=MAX_PROJECTION_YEARS)]
    wacc: Rate = Field(gt=0, lt=1)
    terminal_method: TerminalMethod
    terminal_growth: Rate | None = Field(default=None, gt=Decimal("-0.5"), lt=Decimal("0.5"))
    exit_multiple: Decimal | None = Field(default=None, gt=0, le=100, allow_inf_nan=False)
    terminal_ebitda: Amount | None = None
    mid_year_convention: bool = False
    net_debt: Amount  # total debt - cash; negative means net cash
    other_claims: Amount = Field(default=Decimal(0), ge=0)  # minority interest + preferred
    shares_outstanding: Amount = Field(gt=0)

    @model_validator(mode="after")
    def _validate_terminal(self) -> Self:
        if self.terminal_method == TerminalMethod.PERPETUITY_GROWTH:
            if self.terminal_growth is None:
                raise ValueError("terminal_growth is required for the perpetuity growth method")
            if self.exit_multiple is not None:
                raise ValueError("exit_multiple is only used with the exit multiple method")
            if self.terminal_growth >= self.wacc:
                raise ValueError(
                    f"terminal_growth ({self.terminal_growth}) must be below wacc ({self.wacc})"
                )
            if self.free_cash_flows[-1] * (1 + self.terminal_growth) <= 0:
                raise ValueError(
                    "final-year free cash flow must be positive for the perpetuity growth method"
                )
        else:
            if self.terminal_growth is not None:
                raise ValueError("terminal_growth is only used with the perpetuity growth method")
            if self.exit_multiple is None or self.terminal_ebitda is None:
                raise ValueError(
                    "exit_multiple and terminal_ebitda are required for the exit multiple method"
                )
        if self.terminal_ebitda is not None and self.terminal_ebitda <= 0:
            raise ValueError("terminal_ebitda must be positive")
        return self


class DCFYear(DomainModel):
    year: int
    free_cash_flow: Decimal
    discount_period: Decimal
    discount_factor: Decimal
    present_value: Decimal


class DCFResult(DomainModel):
    currency: CurrencyCode
    scale: Scale
    terminal_method: TerminalMethod
    years: list[DCFYear]
    sum_pv_fcf: Decimal
    terminal_value: Decimal
    pv_terminal_value: Decimal
    enterprise_value: Decimal
    equity_value: Decimal
    value_per_share: Decimal | None
    terminal_value_share: Decimal  # PV(TV) / EV
    implied_exit_multiple: Decimal | None
    implied_terminal_growth: Decimal | None
    warnings: list[Issue]


def run_dcf(inputs: DCFInputs) -> DCFResult:
    one_plus_wacc = 1 + inputs.wacc
    offset = Decimal("0.5") if inputs.mid_year_convention else Decimal(0)

    years: list[DCFYear] = []
    for index, fcf in enumerate(inputs.free_cash_flows, start=1):
        period = Decimal(index) - offset
        factor = 1 / one_plus_wacc**period
        years.append(
            DCFYear(
                year=index,
                free_cash_flow=fcf,
                discount_period=period,
                discount_factor=factor,
                present_value=fcf * factor,
            )
        )

    n = len(inputs.free_cash_flows)
    final_fcf = inputs.free_cash_flows[-1]
    implied_multiple: Decimal | None = None
    implied_growth: Decimal | None = None

    if inputs.terminal_method == TerminalMethod.PERPETUITY_GROWTH:
        assert inputs.terminal_growth is not None  # noqa: S101 - guaranteed by validator
        g = inputs.terminal_growth
        terminal_value = final_fcf * (1 + g) / (inputs.wacc - g)
        if inputs.terminal_ebitda is not None:
            implied_multiple = terminal_value / inputs.terminal_ebitda
    else:
        assert inputs.exit_multiple is not None and inputs.terminal_ebitda is not None  # noqa: S101
        terminal_value = inputs.terminal_ebitda * inputs.exit_multiple
        denominator = terminal_value + final_fcf
        if denominator != 0:
            implied_growth = (terminal_value * inputs.wacc - final_fcf) / denominator

    pv_tv = terminal_value / one_plus_wacc**n
    sum_pv = sum((y.present_value for y in years), Decimal(0))
    ev = sum_pv + pv_tv
    equity = ev - inputs.net_debt - inputs.other_claims
    per_share = equity / inputs.shares_outstanding if equity > 0 else None
    tv_share = pv_tv / ev if ev > 0 else Decimal(1)

    return DCFResult(
        currency=inputs.currency,
        scale=inputs.scale,
        terminal_method=inputs.terminal_method,
        years=years,
        sum_pv_fcf=sum_pv,
        terminal_value=terminal_value,
        pv_terminal_value=pv_tv,
        enterprise_value=ev,
        equity_value=equity,
        value_per_share=per_share,
        terminal_value_share=tv_share,
        implied_exit_multiple=implied_multiple,
        implied_terminal_growth=implied_growth,
        warnings=_warnings(inputs, ev, equity, tv_share, implied_growth),
    )


def _warnings(
    inputs: DCFInputs,
    ev: Decimal,
    equity: Decimal,
    tv_share: Decimal,
    implied_growth: Decimal | None,
) -> list[Issue]:
    out: list[Issue] = []
    g = inputs.terminal_growth
    if g is not None and g > Decimal("0.04"):
        out.append(
            Issue(
                code="high_terminal_growth",
                message=f"Terminal growth {g} exceeds 4%, above typical long-run nominal GDP.",
            )
        )
    if g is not None and inputs.wacc - g < Decimal("0.02"):
        out.append(
            Issue(
                code="terminal_growth_near_wacc",
                message="WACC - g is under 2pp; terminal value is highly sensitive to inputs.",
            )
        )
    if not Decimal("0.04") <= inputs.wacc <= Decimal("0.20"):
        out.append(
            Issue(code="unusual_wacc", message=f"WACC {inputs.wacc} is outside the 4%-20% band.")
        )
    if implied_growth is not None and implied_growth > Decimal("0.04"):
        out.append(
            Issue(
                code="exit_multiple_implies_high_growth",
                message=f"Exit multiple implies perpetual growth of {implied_growth:.4f}.",
            )
        )
    if ev <= 0:
        out.append(Issue(code="non_positive_enterprise_value", message="Enterprise value <= 0."))
    elif tv_share > Decimal("0.75"):
        out.append(
            Issue(
                code="terminal_value_dominant",
                message=f"Terminal value is {tv_share:.1%} of enterprise value.",
            )
        )
    if equity <= 0:
        out.append(
            Issue(
                code="non_positive_equity_value",
                message="Equity value <= 0; per-share value is not meaningful.",
            )
        )
    if any(fcf < 0 for fcf in inputs.free_cash_flows):
        out.append(
            Issue(
                code="negative_fcf_years",
                severity=IssueSeverity.INFO,
                message="One or more projection years have negative free cash flow.",
            )
        )
    return out


# --- Sensitivity -------------------------------------------------------------------------------

SensitivityOutput = Literal["value_per_share", "enterprise_value", "equity_value"]


class SensitivityTable(DomainModel):
    output: SensitivityOutput
    row_axis: Literal["wacc"] = "wacc"
    column_axis: Literal["terminal_growth", "exit_multiple"]
    row_values: list[Decimal]
    column_values: list[Decimal]
    cells: list[list[Decimal | None]]  # cells[row][column]; None = invalid combination
    invalid_reasons: dict[str, str]  # "row,col" -> reason


def build_axis(center: Decimal, step: Decimal, count: int = 5) -> list[Decimal]:
    """``count`` evenly spaced values centred on ``center`` (count must be odd)."""
    if count < 1 or count % 2 == 0 or count > MAX_SENSITIVITY_AXIS:
        raise ValueError(f"count must be odd and between 1 and {MAX_SENSITIVITY_AXIS}")
    if step <= 0:
        raise ValueError("step must be positive")
    half = count // 2
    return [center + step * (i - half) for i in range(count)]


def sensitivity(
    inputs: DCFInputs,
    wacc_values: Sequence[Decimal],
    column_values: Sequence[Decimal],
    output: SensitivityOutput = "value_per_share",
) -> SensitivityTable:
    """Re-run the DCF across WACC x (terminal growth | exit multiple)."""
    if not (1 <= len(wacc_values) <= MAX_SENSITIVITY_AXIS) or not (
        1 <= len(column_values) <= MAX_SENSITIVITY_AXIS
    ):
        raise ValueError(f"each axis must have 1..{MAX_SENSITIVITY_AXIS} values")
    column_field: Literal["terminal_growth", "exit_multiple"] = (
        "terminal_growth"
        if inputs.terminal_method == TerminalMethod.PERPETUITY_GROWTH
        else "exit_multiple"
    )
    base = inputs.model_dump()
    cells: list[list[Decimal | None]] = []
    reasons: dict[str, str] = {}
    for r, wacc in enumerate(wacc_values):
        row: list[Decimal | None] = []
        for c, column_value in enumerate(column_values):
            try:
                variant = DCFInputs.model_validate(
                    {**base, "wacc": wacc, column_field: column_value}
                )
            except ValidationError as exc:
                row.append(None)
                reasons[f"{r},{c}"] = exc.errors()[0]["msg"]
                continue
            result = run_dcf(variant)
            value = getattr(result, output)
            row.append(value)
            if value is None:
                reasons[f"{r},{c}"] = "equity value <= 0"
        cells.append(row)
    return SensitivityTable(
        output=output,
        column_axis=column_field,
        row_values=list(wacc_values),
        column_values=list(column_values),
        cells=cells,
        invalid_reasons=reasons,
    )
