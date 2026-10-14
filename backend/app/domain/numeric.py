"""Small exact-arithmetic helpers on Decimal."""

from collections.abc import Sequence
from decimal import Decimal


def mean(values: Sequence[Decimal]) -> Decimal:
    if not values:
        raise ValueError("mean of empty sequence")
    return sum(values, Decimal(0)) / len(values)


def percentile(values: Sequence[Decimal], p: Decimal) -> Decimal:
    """Percentile with linear interpolation between closest ranks.

    Matches numpy's default ("linear") method: position = (n - 1) * p.
    """
    if not values:
        raise ValueError("percentile of empty sequence")
    if not Decimal(0) <= p <= Decimal(1):
        raise ValueError("p must be within [0, 1]")
    ordered = sorted(values)
    position = (len(ordered) - 1) * p
    lower = int(position)  # floor, position is non-negative
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def median(values: Sequence[Decimal]) -> Decimal:
    return percentile(values, Decimal("0.5"))
