"""Driver-based free cash flow forecast with bull / base / bear scenarios.

For each forecast year t (t = 1..N), starting from base-year revenue R_0:

    revenue_t        = revenue_{t-1} * (1 + revenue_growth_t)
    ebit_t           = revenue_t * ebit_margin_t
    taxes_t          = max(ebit_t, 0) * tax_rate        (losses create no tax credit)
    nopat_t          = ebit_t - taxes_t
    d_and_a_t        = revenue_t * da_pct_revenue
    capex_t          = revenue_t * capex_pct_revenue
    nwc_t            = revenue_t * nwc_pct_revenue
    change_in_nwc_t  = nwc_t - nwc_{t-1}               (nwc_0 = base_nwc, or R_0 * nwc_pct_revenue)
    fcf_t            = nopat_t + d_and_a_t - capex_t - change_in_nwc_t

All outputs are ``ValueKind.FORECAST``; they are estimates driven entirely by the assumptions.
"""

from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Self

from pydantic import Field, model_validator

from app.domain.dcf import MAX_PROJECTION_YEARS
from app.domain.types import (
    Amount,
    CurrencyCode,
    DomainModel,
    Issue,
    Rate,
    Scale,
    ValueKind,
)

GrowthRate = Annotated[Rate, Field(gt=-1, le=5)]
Margin = Annotated[Rate, Field(ge=-1, le=1)]


class ScenarioName(StrEnum):
    BULL = "bull"
    BASE = "base"
    BEAR = "bear"


class ForecastAssumptions(DomainModel):
    revenue_growth: Annotated[
        list[GrowthRate], Field(min_length=1, max_length=MAX_PROJECTION_YEARS)
    ]
    ebit_margin: Annotated[list[Margin], Field(min_length=1, max_length=MAX_PROJECTION_YEARS)]
    tax_rate: Rate = Field(ge=0, lt=1)
    da_pct_revenue: Rate = Field(ge=0, le=1)
    capex_pct_revenue: Rate = Field(ge=0, le=1)
    nwc_pct_revenue: Rate = Field(ge=-1, le=1)

    @model_validator(mode="after")
    def _same_horizon(self) -> Self:
        if len(self.revenue_growth) != len(self.ebit_margin):
            raise ValueError("revenue_growth and ebit_margin must cover the same number of years")
        return self


class ForecastBase(DomainModel):
    base_year: int = Field(ge=1900, le=2200)
    base_revenue: Amount = Field(gt=0)
    base_nwc: Amount | None = None
    currency: CurrencyCode
    scale: Scale


class ForecastYear(DomainModel):
    year: int
    revenue: Decimal
    ebit: Decimal
    taxes: Decimal
    nopat: Decimal
    d_and_a: Decimal
    capex: Decimal
    nwc: Decimal
    change_in_nwc: Decimal
    free_cash_flow: Decimal


class ForecastResult(DomainModel):
    scenario: ScenarioName
    currency: CurrencyCode
    scale: Scale
    kind: ValueKind = ValueKind.FORECAST
    assumptions: ForecastAssumptions
    years: list[ForecastYear]
    notes: list[str]

    @property
    def free_cash_flows(self) -> list[Decimal]:
        return [y.free_cash_flow for y in self.years]


class ScenarioSetResult(DomainModel):
    scenarios: dict[ScenarioName, ForecastResult]
    warnings: list[Issue]


def project(
    base: ForecastBase, assumptions: ForecastAssumptions, scenario: ScenarioName
) -> ForecastResult:
    notes: list[str] = []
    if base.base_nwc is None:
        previous_nwc = base.base_revenue * assumptions.nwc_pct_revenue
        notes.append("base-year NWC assumed equal to base_revenue * nwc_pct_revenue")
    else:
        previous_nwc = base.base_nwc

    revenue = base.base_revenue
    years: list[ForecastYear] = []
    for index, (growth, margin) in enumerate(
        zip(assumptions.revenue_growth, assumptions.ebit_margin, strict=True), start=1
    ):
        revenue = revenue * (1 + growth)
        ebit = revenue * margin
        taxes = max(ebit, Decimal(0)) * assumptions.tax_rate
        nopat = ebit - taxes
        d_and_a = revenue * assumptions.da_pct_revenue
        capex = revenue * assumptions.capex_pct_revenue
        nwc = revenue * assumptions.nwc_pct_revenue
        change_in_nwc = nwc - previous_nwc
        years.append(
            ForecastYear(
                year=base.base_year + index,
                revenue=revenue,
                ebit=ebit,
                taxes=taxes,
                nopat=nopat,
                d_and_a=d_and_a,
                capex=capex,
                nwc=nwc,
                change_in_nwc=change_in_nwc,
                free_cash_flow=nopat + d_and_a - capex - change_in_nwc,
            )
        )
        previous_nwc = nwc

    return ForecastResult(
        scenario=scenario,
        currency=base.currency,
        scale=base.scale,
        assumptions=assumptions,
        years=years,
        notes=notes,
    )


def run_scenarios(
    base: ForecastBase, scenarios: dict[ScenarioName, ForecastAssumptions]
) -> ScenarioSetResult:
    if ScenarioName.BASE not in scenarios:
        raise ValueError("a base scenario is required")
    horizons = {len(a.revenue_growth) for a in scenarios.values()}
    if len(horizons) != 1:
        raise ValueError("all scenarios must use the same forecast horizon")

    results = {name: project(base, a, name) for name, a in scenarios.items()}

    warnings: list[Issue] = []
    final_revenue = {name: r.years[-1].revenue for name, r in results.items()}
    base_final = final_revenue[ScenarioName.BASE]
    if ScenarioName.BULL in final_revenue and final_revenue[ScenarioName.BULL] < base_final:
        warnings.append(
            Issue(code="bull_below_base", message="Bull final-year revenue is below base.")
        )
    if ScenarioName.BEAR in final_revenue and final_revenue[ScenarioName.BEAR] > base_final:
        warnings.append(
            Issue(code="bear_above_base", message="Bear final-year revenue is above base.")
        )
    return ScenarioSetResult(scenarios=results, warnings=warnings)
