from typing import Any

import pytest
from pydantic import ValidationError

from app.domain.dcf import DCFInputs, run_dcf
from app.domain.forecast import (
    ForecastAssumptions,
    ForecastBase,
    ScenarioName,
    project,
    run_scenarios,
)
from tests.domain.helpers import D

BASE = ForecastBase(base_year=2025, base_revenue=D(1000), currency="USD", scale="millions")
ASSUMPTIONS: dict[str, Any] = {
    "revenue_growth": [D("0.1"), D("0.1")],
    "ebit_margin": [D("0.2"), D("0.2")],
    "tax_rate": D("0.25"),
    "da_pct_revenue": D("0.05"),
    "capex_pct_revenue": D("0.06"),
    "nwc_pct_revenue": D("0.1"),
}


def assumptions(**overrides: Any) -> ForecastAssumptions:
    return ForecastAssumptions.model_validate(ASSUMPTIONS | overrides)


def test_projection_hand_computed() -> None:
    r = project(BASE, assumptions(), ScenarioName.BASE)
    y1, y2 = r.years
    assert (y1.year, y1.revenue, y1.ebit, y1.taxes, y1.nopat) == (
        2026,
        D(1100),
        D(220),
        D(55),
        D(165),
    )
    assert (y1.d_and_a, y1.capex, y1.nwc, y1.change_in_nwc) == (D(55), D(66), D(110), D(10))
    assert y1.free_cash_flow == D(144)  # 165 + 55 - 66 - 10
    assert y2.revenue == D(1210)
    assert y2.change_in_nwc == D(11)
    assert y2.free_cash_flow == D("158.4")  # 181.5 + 60.5 - 72.6 - 11
    assert r.kind == "forecast"
    assert r.notes == ["base-year NWC assumed equal to base_revenue * nwc_pct_revenue"]


def test_reported_base_nwc_is_used() -> None:
    base = BASE.model_copy(update={"base_nwc": D(80)})
    r = project(base, assumptions(), ScenarioName.BASE)
    assert r.years[0].change_in_nwc == D(30)
    assert r.notes == []


def test_operating_loss_pays_no_tax() -> None:
    r = project(BASE, assumptions(ebit_margin=[D("-0.1"), D("0.2")]), ScenarioName.BEAR)
    assert r.years[0].taxes == 0
    assert r.years[0].nopat == D(-110)


@pytest.mark.parametrize(
    "overrides",
    [
        {"revenue_growth": [D("0.1")]},  # horizon mismatch
        {"revenue_growth": [D(-1), D("0.1")]},  # -100% growth
        {"ebit_margin": [D("1.5"), D("0.2")]},
        {"tax_rate": D(1)},
        {"capex_pct_revenue": D(-0.1)},
        {"revenue_growth": [], "ebit_margin": []},
    ],
)
def test_invalid_assumptions(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        assumptions(**overrides)


def test_scenarios_and_sanity_warnings() -> None:
    bull = assumptions(revenue_growth=[D("0.2"), D("0.2")])
    bear = assumptions(revenue_growth=[D("0.0"), D("0.0")])
    result = run_scenarios(
        BASE, {ScenarioName.BULL: bull, ScenarioName.BASE: assumptions(), ScenarioName.BEAR: bear}
    )
    assert result.warnings == []
    finals = {k: v.years[-1].revenue for k, v in result.scenarios.items()}
    assert finals[ScenarioName.BULL] > finals[ScenarioName.BASE] > finals[ScenarioName.BEAR]

    swapped = run_scenarios(BASE, {ScenarioName.BULL: bear, ScenarioName.BASE: assumptions()})
    assert [w.code for w in swapped.warnings] == ["bull_below_base"]


def test_scenario_validation() -> None:
    with pytest.raises(ValueError, match="base scenario is required"):
        run_scenarios(BASE, {ScenarioName.BULL: assumptions()})
    three_years = assumptions(revenue_growth=[D("0.1")] * 3, ebit_margin=[D("0.2")] * 3)
    with pytest.raises(ValueError, match="same forecast horizon"):
        run_scenarios(BASE, {ScenarioName.BASE: assumptions(), ScenarioName.BEAR: three_years})


def test_forecast_feeds_dcf() -> None:
    forecast = project(BASE, assumptions(), ScenarioName.BASE)
    dcf = run_dcf(
        DCFInputs(
            currency=forecast.currency,
            scale=forecast.scale,
            free_cash_flows=forecast.free_cash_flows,
            wacc=D("0.09"),
            terminal_method="perpetuity_growth",
            terminal_growth=D("0.025"),
            net_debt=D(100),
            shares_outstanding=D(50),
        )
    )
    assert dcf.years[1].free_cash_flow == D("158.4")
    assert dcf.value_per_share is not None and dcf.value_per_share > 0
