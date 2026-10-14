"""Comparable company (trading multiples) analysis.

Peer multiples:
    EV / Revenue  = enterprise_value / revenue
    EV / EBITDA   = enterprise_value / ebitda
    P / E         = market_cap / net_income
    P / B         = market_cap / book_equity

    enterprise_value = reported EV, else market_cap + net_debt + other_claims

A peer is excluded from a multiple (with a recorded reason) when an input is missing or the
denominator is <= 0 (negative earnings make P/E meaningless). The target itself is never used
as its own peer. Amounts are rescaled to the target's scale; differing currencies are rejected
(currency conversion belongs in the data layer, with a documented FX source).

Implied target valuation per multiple uses the peer median (low/high = 25th/75th percentile):
    EV multiples:     implied_ev = multiple * target_metric
                      implied_equity = implied_ev - target.net_debt - target.other_claims
    equity multiples: implied_equity = multiple * target_metric
    implied_per_share = implied_equity / target.shares_outstanding
"""

from collections.abc import Sequence
from decimal import Decimal
from enum import StrEnum

from pydantic import Field

from app.domain.numeric import mean, median, percentile
from app.domain.types import Amount, CurrencyCode, DomainModel, Issue, Scale, rescale

MIN_RECOMMENDED_PEERS = 3


class Multiple(StrEnum):
    EV_REVENUE = "ev_revenue"
    EV_EBITDA = "ev_ebitda"
    PRICE_EARNINGS = "price_earnings"
    PRICE_BOOK = "price_book"


# multiple -> (numerator basis, denominator field)
_DEFINITIONS: dict[Multiple, tuple[str, str]] = {
    Multiple.EV_REVENUE: ("enterprise_value", "revenue"),
    Multiple.EV_EBITDA: ("enterprise_value", "ebitda"),
    Multiple.PRICE_EARNINGS: ("market_cap", "net_income"),
    Multiple.PRICE_BOOK: ("market_cap", "book_equity"),
}


class CompanyMetrics(DomainModel):
    company: str = Field(min_length=1, max_length=50)
    currency: CurrencyCode
    scale: Scale
    market_cap: Amount = Field(gt=0)
    enterprise_value: Amount | None = None
    net_debt: Amount | None = None
    other_claims: Amount = Field(default=Decimal(0), ge=0)
    revenue: Amount | None = None
    ebitda: Amount | None = None
    net_income: Amount | None = None
    book_equity: Amount | None = None
    shares_outstanding: Amount | None = Field(default=None, gt=0)

    def resolved_enterprise_value(self) -> Decimal | None:
        if self.enterprise_value is not None:
            return self.enterprise_value
        if self.net_debt is None:
            return None
        return self.market_cap + self.net_debt + self.other_claims

    def value_of(self, field: str, to_scale: Scale) -> Decimal | None:
        raw = (
            self.resolved_enterprise_value()
            if field == "enterprise_value"
            else getattr(self, field)
        )
        return None if raw is None else rescale(raw, self.scale, to_scale)


class MultipleStats(DomainModel):
    multiple: Multiple
    values: dict[str, Decimal]  # peer -> multiple
    excluded: dict[str, str]  # peer -> reason
    count: int
    minimum: Decimal | None
    p25: Decimal | None
    median: Decimal | None
    mean: Decimal | None
    p75: Decimal | None
    maximum: Decimal | None


class ImpliedValuation(DomainModel):
    multiple: Multiple
    target_metric: Decimal | None
    implied_enterprise_value: Decimal | None
    implied_equity_value: Decimal | None
    implied_value_per_share: Decimal | None
    low_value_per_share: Decimal | None  # at peer p25
    high_value_per_share: Decimal | None  # at peer p75
    note: str | None


class CompsResult(DomainModel):
    target: str
    currency: CurrencyCode
    scale: Scale
    stats: dict[Multiple, MultipleStats]
    implied: dict[Multiple, ImpliedValuation]
    warnings: list[Issue]


def _peer_stats(
    multiple: Multiple, peers: Sequence[CompanyMetrics], target: CompanyMetrics
) -> MultipleStats:
    numerator_field, denominator_field = _DEFINITIONS[multiple]
    values: dict[str, Decimal] = {}
    excluded: dict[str, str] = {}
    for peer in peers:
        if peer.company == target.company:
            excluded[peer.company] = "target company"
            continue
        num = peer.value_of(numerator_field, target.scale)
        den = peer.value_of(denominator_field, target.scale)
        if num is None or den is None:
            missing = [
                name
                for name, value in ((numerator_field, num), (denominator_field, den))
                if value is None
            ]
            excluded[peer.company] = f"missing {', '.join(missing)}"
        elif den <= 0:
            excluded[peer.company] = f"non-positive {denominator_field} ({den})"
        elif num <= 0:
            excluded[peer.company] = f"non-positive {numerator_field} ({num})"
        else:
            values[peer.company] = num / den

    series = list(values.values())
    has = bool(series)
    return MultipleStats(
        multiple=multiple,
        values=values,
        excluded=excluded,
        count=len(series),
        minimum=min(series) if has else None,
        p25=percentile(series, Decimal("0.25")) if has else None,
        median=median(series) if has else None,
        mean=mean(series) if has else None,
        p75=percentile(series, Decimal("0.75")) if has else None,
        maximum=max(series) if has else None,
    )


def _implied(stats: MultipleStats, target: CompanyMetrics) -> ImpliedValuation:
    numerator_field, denominator_field = _DEFINITIONS[stats.multiple]
    metric = getattr(target, denominator_field)

    def empty(note: str) -> ImpliedValuation:
        return ImpliedValuation(
            multiple=stats.multiple,
            target_metric=metric,
            implied_enterprise_value=None,
            implied_equity_value=None,
            implied_value_per_share=None,
            low_value_per_share=None,
            high_value_per_share=None,
            note=note,
        )

    if stats.median is None or stats.p25 is None or stats.p75 is None:
        return empty("no usable peer multiples")
    if metric is None:
        return empty(f"target {denominator_field} missing")
    if metric <= 0:
        return empty(f"target {denominator_field} is non-positive; multiple not applicable")

    is_ev_multiple = numerator_field == "enterprise_value"
    if is_ev_multiple and target.net_debt is None:
        return empty("target net_debt missing; cannot bridge EV to equity")

    def equity_at(multiple_value: Decimal) -> tuple[Decimal | None, Decimal]:
        value = multiple_value * metric
        if is_ev_multiple:
            assert target.net_debt is not None  # noqa: S101 - checked above
            return value, value - target.net_debt - target.other_claims
        return None, value

    def per_share(equity: Decimal) -> Decimal | None:
        if target.shares_outstanding is None or equity <= 0:
            return None
        return equity / target.shares_outstanding

    ev, equity = equity_at(stats.median)
    _, low_equity = equity_at(stats.p25)
    _, high_equity = equity_at(stats.p75)
    note = None
    if target.shares_outstanding is None:
        note = "target shares_outstanding missing; per-share values unavailable"
    elif equity <= 0:
        note = "implied equity value <= 0"
    return ImpliedValuation(
        multiple=stats.multiple,
        target_metric=metric,
        implied_enterprise_value=ev,
        implied_equity_value=equity,
        implied_value_per_share=per_share(equity),
        low_value_per_share=per_share(low_equity),
        high_value_per_share=per_share(high_equity),
        note=note,
    )


def analyze_comps(
    target: CompanyMetrics,
    peers: Sequence[CompanyMetrics],
    multiples: Sequence[Multiple] = tuple(Multiple),
) -> CompsResult:
    if not peers:
        raise ValueError("at least one peer is required")
    mismatched = sorted({p.company for p in peers if p.currency != target.currency})
    if mismatched:
        raise ValueError(
            f"peers {mismatched} are not in {target.currency}; convert currencies first"
        )
    if len({p.company for p in peers}) != len(peers):
        raise ValueError("duplicate peer companies")

    stats = {m: _peer_stats(m, peers, target) for m in multiples}
    implied = {m: _implied(s, target) for m, s in stats.items()}

    warnings = [
        Issue(
            code="few_peers",
            message=f"{m.value}: only {s.count} usable peer(s); "
            f"{MIN_RECOMMENDED_PEERS}+ recommended.",
        )
        for m, s in stats.items()
        if s.count < MIN_RECOMMENDED_PEERS
    ]
    return CompsResult(
        target=target.company,
        currency=target.currency,
        scale=target.scale,
        stats=stats,
        implied=implied,
        warnings=warnings,
    )
