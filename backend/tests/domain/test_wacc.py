from typing import Any

import pytest
from pydantic import ValidationError

from app.domain.wacc import WACCInputs, compute_wacc
from tests.domain.helpers import D, approx

BASE: dict[str, Any] = {
    "risk_free_rate": D("0.04"),
    "equity_risk_premium": D("0.05"),
    "beta": D("1.2"),
    "pre_tax_cost_of_debt": D("0.06"),
    "tax_rate": D("0.25"),
    "equity_value": D(800),
    "debt_value": D(200),
}


def test_wacc_hand_computed() -> None:
    r = compute_wacc(WACCInputs.model_validate(BASE))
    assert approx(r.cost_of_equity, "0.10")  # 0.04 + 1.2 * 0.05
    assert approx(r.after_tax_cost_of_debt, "0.045")  # 0.06 * 0.75
    assert approx(r.equity_weight, "0.8")
    assert approx(r.debt_weight, "0.2")
    assert approx(r.wacc, "0.089")  # 0.8 * 0.10 + 0.2 * 0.045
    assert r.warnings == []


def test_size_premium_and_all_equity() -> None:
    r = compute_wacc(WACCInputs.model_validate(BASE | {"size_premium": D("0.02"), "debt_value": 0}))
    assert approx(r.wacc, "0.12")


def test_unusual_wacc_warning() -> None:
    r = compute_wacc(WACCInputs.model_validate(BASE | {"beta": D("4"), "debt_value": 0}))
    assert [w.code for w in r.warnings] == ["unusual_wacc"]


def test_non_positive_wacc_rejected() -> None:
    with pytest.raises(ValueError, match="must be positive"):
        compute_wacc(
            WACCInputs.model_validate(
                BASE | {"risk_free_rate": D("-0.05"), "beta": D(0), "debt_value": 0}
            )
        )


@pytest.mark.parametrize(
    "overrides",
    [{"tax_rate": D(1)}, {"equity_value": D(0)}, {"debt_value": D(-1)}, {"beta": D(9)}],
)
def test_invalid_inputs(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        WACCInputs.model_validate(BASE | overrides)
