from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from app.domain.dcf import DCFInputs, TerminalMethod, build_axis, run_dcf, sensitivity
from tests.domain.helpers import D, approx

BASE: dict[str, Any] = {
    "currency": "USD",
    "scale": "millions",
    "free_cash_flows": [D(100), D(110), D(121)],
    "wacc": D("0.10"),
    "terminal_method": "perpetuity_growth",
    "terminal_growth": D("0.02"),
    "net_debt": D(200),
    "shares_outstanding": D(10),
}


def inputs(**overrides: Any) -> DCFInputs:
    return DCFInputs.model_validate(BASE | overrides)


def test_perpetuity_growth_hand_computed() -> None:
    # Each FCF grows 10% and is discounted at 10%, so every PV is 100/1.1 = 1000/11.
    r = run_dcf(inputs())
    for year in r.years:
        assert approx(year.present_value, D(1000) / D(11))
    assert approx(r.sum_pv_fcf, D(3000) / D(11))
    assert r.terminal_value == D("1542.75")  # 121 * 1.02 / 0.08
    assert approx(r.pv_terminal_value, D(12750) / D(11))  # 1542.75 / 1.331
    assert approx(r.enterprise_value, D(15750) / D(11))
    assert approx(r.equity_value, D(13550) / D(11))
    assert approx(r.value_per_share, D(1355) / D(11))
    assert approx(r.terminal_value_share, D(17) / D(21))
    assert r.implied_exit_multiple is None
    assert {w.code for w in r.warnings} == {"terminal_value_dominant"}


def test_implied_exit_multiple_cross_check() -> None:
    r = run_dcf(inputs(terminal_ebitda=D(200)))
    assert approx(r.implied_exit_multiple, "7.71375")


def test_mid_year_convention_scales_explicit_pvs_only() -> None:
    end = run_dcf(inputs())
    mid = run_dcf(inputs(mid_year_convention=True))
    factor = D("1.1").sqrt()
    assert [y.discount_period for y in mid.years] == [D("0.5"), D("1.5"), D("2.5")]
    assert abs(mid.sum_pv_fcf - end.sum_pv_fcf * factor) < D("1e-15")
    assert mid.pv_terminal_value == end.pv_terminal_value


def test_exit_multiple_method() -> None:
    r = run_dcf(
        inputs(
            terminal_method="exit_multiple",
            terminal_growth=None,
            exit_multiple=D(8),
            terminal_ebitda=D(200),
        )
    )
    assert r.terminal_value == D(1600)
    assert approx(r.pv_terminal_value, D(1600) / D("1.331"))
    # g = (TV * wacc - FCF_N) / (TV + FCF_N) = (160 - 121) / 1721
    assert approx(r.implied_terminal_growth, D(39) / D(1721))


def test_net_cash_increases_equity_value() -> None:
    r = run_dcf(inputs(net_debt=D(-100)))
    assert approx(r.equity_value, D(15750) / D(11) + 100)


def test_negative_equity_has_no_per_share_value() -> None:
    r = run_dcf(inputs(net_debt=D(5000)))
    assert r.value_per_share is None
    assert "non_positive_equity_value" in {w.code for w in r.warnings}


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"terminal_growth": D("0.10")}, "must be below wacc"),
        ({"terminal_growth": D("0.12")}, "must be below wacc"),
        ({"terminal_growth": None}, "terminal_growth is required"),
        ({"exit_multiple": D(8)}, "only used with the exit multiple"),
        ({"free_cash_flows": [D(100), D(-5)]}, "final-year free cash flow must be positive"),
        ({"free_cash_flows": []}, "at least 1"),
        ({"free_cash_flows": [D(1)] * 31}, "at most 30"),
        ({"wacc": D(0)}, "greater than 0"),
        ({"wacc": D(1)}, "less than 1"),
        ({"wacc": Decimal("NaN")}, "finite number"),
        ({"shares_outstanding": D(0)}, "greater than 0"),
        ({"other_claims": D(-1)}, "greater than or equal to 0"),
        ({"terminal_ebitda": D(-1)}, "terminal_ebitda must be positive"),
        ({"currency": "usd"}, "pattern"),
        (
            {"terminal_method": "exit_multiple", "terminal_growth": None, "exit_multiple": D(8)},
            "required for the exit multiple",
        ),
        (
            {"terminal_method": "exit_multiple", "exit_multiple": D(8), "terminal_ebitda": D(9)},
            "only used with the perpetuity",
        ),
    ],
)
def test_invalid_assumptions_rejected(overrides: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        inputs(**overrides)


def test_warnings_for_aggressive_assumptions() -> None:
    r = run_dcf(inputs(wacc=D("0.06"), terminal_growth=D("0.05")))
    codes = {w.code for w in r.warnings}
    assert {"high_terminal_growth", "terminal_growth_near_wacc", "terminal_value_dominant"} <= codes


def test_negative_interim_fcf_is_flagged_info() -> None:
    r = run_dcf(inputs(free_cash_flows=[D(-50), D(100)]))
    (issue,) = [w for w in r.warnings if w.code == "negative_fcf_years"]
    assert issue.severity == "info"


# --- sensitivity ------------------------------------------------------------------------------


def test_build_axis() -> None:
    assert build_axis(D("0.10"), D("0.01")) == [
        D("0.08"),
        D("0.09"),
        D("0.10"),
        D("0.11"),
        D("0.12"),
    ]
    with pytest.raises(ValueError):
        build_axis(D("0.1"), D("0.01"), count=4)
    with pytest.raises(ValueError):
        build_axis(D("0.1"), D(0))


def test_sensitivity_grid_centre_matches_base_and_is_monotonic() -> None:
    base = inputs()
    waccs = build_axis(D("0.10"), D("0.01"), 3)
    growths = build_axis(D("0.02"), D("0.005"), 3)
    table = sensitivity(base, waccs, growths)
    assert table.column_axis == "terminal_growth"
    assert table.cells[1][1] == run_dcf(base).value_per_share
    for row in table.cells:  # higher growth -> higher value
        values = [v for v in row if v is not None]
        assert values == sorted(values)
    for col in range(3):  # higher WACC -> lower value
        values = [row[col] for row in table.cells]
        assert all(v is not None for v in values)
        assert values == sorted(values, reverse=True)  # type: ignore[type-var]
    assert table.invalid_reasons == {}


def test_sensitivity_marks_invalid_combinations() -> None:
    table = sensitivity(inputs(), [D("0.02"), D("0.10")], [D("0.03")])
    assert table.cells[0][0] is None
    assert "must be below wacc" in table.invalid_reasons["0,0"]
    assert table.cells[1][0] is not None


def test_sensitivity_exit_multiple_axis() -> None:
    exit_inputs = inputs(
        terminal_method=TerminalMethod.EXIT_MULTIPLE,
        terminal_growth=None,
        exit_multiple=D(8),
        terminal_ebitda=D(200),
    )
    table = sensitivity(exit_inputs, [D("0.10")], [D(6), D(8), D(10)], output="enterprise_value")
    assert table.column_axis == "exit_multiple"
    assert table.cells[0][1] == run_dcf(exit_inputs).enterprise_value


def test_sensitivity_axis_size_limit() -> None:
    with pytest.raises(ValueError):
        sensitivity(inputs(), [D("0.1")] * 16, [D("0.02")])
