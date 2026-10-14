from decimal import Decimal

TOLERANCE = Decimal("1e-18")


def D(value: str | int) -> Decimal:
    return Decimal(str(value))


def approx(actual: Decimal | None, expected: Decimal | int | str) -> bool:
    assert actual is not None, "expected a value, got None"
    return abs(actual - Decimal(str(expected))) < TOLERANCE
