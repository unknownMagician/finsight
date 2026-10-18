import ast
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.domain.numeric import mean, median, percentile
from app.domain.statements import CashFlowStatement, IncomeStatement
from app.domain.types import ReportingPeriod, Scale, SourceRef, rescale
from tests.domain.helpers import D

DOMAIN_DIR = Path(__file__).resolve().parents[2] / "app" / "domain"
FORBIDDEN_IMPORTS = {"fastapi", "sqlalchemy", "httpx", "requests", "os", "random", "app.db"}


def test_domain_package_has_no_io_imports() -> None:
    for path in DOMAIN_DIR.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                assert not any(name == f or name.startswith(f"{f}.") for f in FORBIDDEN_IMPORTS), (
                    f"{path.name} imports {name}; domain code must stay pure"
                )


@pytest.mark.parametrize(
    ("value", "src", "dst", "expected"),
    [
        ("1500", Scale.THOUSANDS, Scale.MILLIONS, "1.5"),
        ("2", Scale.BILLIONS, Scale.MILLIONS, "2000"),
        ("7", Scale.UNITS, Scale.UNITS, "7"),
        # Indian scales: 1 crore = 100 lakh = 10 million = 10^7 rupees.
        ("1", Scale.CRORES, Scale.LAKHS, "100"),
        ("1", Scale.CRORES, Scale.MILLIONS, "10"),
        ("10572190000000", Scale.UNITS, Scale.CRORES, "1057219"),
        ("250", Scale.LAKHS, Scale.UNITS, "25000000"),
    ],
)
def test_rescale(value: str, src: Scale, dst: Scale, expected: str) -> None:
    assert rescale(D(value), src, dst) == D(expected)


def test_reporting_period_validation_and_label() -> None:
    period = ReportingPeriod(fiscal_year=2025, period_end=date(2025, 12, 31))
    assert period.label == "FY2025"
    with pytest.raises(ValidationError, match="period_start must be before period_end"):
        ReportingPeriod(
            fiscal_year=2025, period_start=date(2026, 1, 1), period_end=date(2025, 12, 31)
        )


def test_models_are_immutable_and_strict() -> None:
    source = SourceRef(provider="test", retrieved_at=datetime(2026, 1, 1, tzinfo=UTC))
    with pytest.raises(ValidationError):
        source.provider = "other"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        IncomeStatement(revenue=D(1), unexpected_field=D(2))  # type: ignore[call-arg]


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_amounts_rejected(bad: str) -> None:
    with pytest.raises(ValidationError):
        IncomeStatement(revenue=Decimal(bad))


def test_sign_conventions_enforced() -> None:
    with pytest.raises(ValidationError):
        CashFlowStatement(capital_expenditures=D(-5))
    assert CashFlowStatement(capital_expenditures=None).capital_expenditures is None


def test_percentile_matches_linear_interpolation() -> None:
    values = [D(10), D(12), D(10), D(12)]
    assert percentile(values, D("0.25")) == D(10)
    assert percentile(values, D("0.75")) == D(12)
    assert median(values) == D(11)
    assert median([D(1), D(2), D(3), D(4), D(100)]) == D(3)
    assert percentile([D(1), D(2), D(3), D(4)], D("0.5")) == D("2.5")
    assert mean([D(1), D(2), D(6)]) == D(3)


def test_numeric_edge_cases() -> None:
    assert percentile([D(5)], D("0.75")) == D(5)
    with pytest.raises(ValueError):
        median([])
    with pytest.raises(ValueError):
        percentile([D(1)], D("1.5"))
