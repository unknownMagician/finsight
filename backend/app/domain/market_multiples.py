"""Market-based metrics: market cap, enterprise value, P/E, P/B, EV/EBITDA, dividend yield.

Combines one end-of-day closing price (a dated market fact) with one reporting period's
statements. Rules:

- The price currency must equal the statement currency; amounts are rescaled to the
  statement's scale. Price is per share in major units (e.g. rupees).
- Share count is the period-end ``shares_outstanding`` from the balance sheet. If a split,
  bonus or similar share-count event went ex *after* the period end (and on/before the price
  date), the price and the share count / EPS are on different bases, so every per-share
  dependent metric is ``not_meaningful`` rather than silently wrong.
- Enterprise value = market_cap + total_debt + minority_interest + preferred_equity
  - cash_and_equivalents. Debt and cash are required; minority interest and preferred equity
  are added when reported, and the metric's note says when they were not reported.
- Negative or zero denominators (losses, negative EBITDA, negative equity) give
  ``not_meaningful``; nothing is clamped or estimated.
"""

from datetime import date
from decimal import Decimal

from pydantic import Field

from app.domain.ratios import MetricResult, MetricUnit, _amount, _divide, ebitda, total_debt
from app.domain.statements import FinancialPeriodData
from app.domain.types import (
    CurrencyCode,
    DomainModel,
    Issue,
    IssueSeverity,
    ReportingPeriod,
    Scale,
    rescale,
)

# Fundamentals older than this relative to the price date are flagged.
STALE_FUNDAMENTALS_DAYS = 456  # ~15 months: one annual cycle plus the filing window


class MarketPrice(DomainModel):
    price: Decimal = Field(gt=0, allow_inf_nan=False)
    price_date: date
    currency: CurrencyCode
    source: str = Field(min_length=1, max_length=200)


class MarketMultiplesReport(DomainModel):
    company: str
    period: ReportingPeriod
    price: MarketPrice
    currency: CurrencyCode
    scale: Scale
    metrics: dict[str, MetricResult]
    issues: list[Issue]


def _blocked(name: str, unit: MetricUnit, formula: str, reason: str) -> MetricResult:
    return MetricResult(
        name=name,
        value=None,
        unit=unit,
        formula=formula,
        inputs={},
        status="not_meaningful",
        note=reason,
    )


def compute_market_multiples(
    data: FinancialPeriodData,
    price: MarketPrice,
    *,
    share_count_events_after_period: list[str] | None = None,
    trailing_dividends_per_share: Decimal | None = None,
    dividends_note: str | None = None,
) -> MarketMultiplesReport:
    if price.currency != data.currency:
        raise ValueError(
            f"price currency {price.currency} differs from statement currency {data.currency}"
        )
    if price.price_date < data.period.period_end:
        raise ValueError("price date must be on or after the period end")

    issues: list[Issue] = []
    age = (price.price_date - data.period.period_end).days
    if age > STALE_FUNDAMENTALS_DAYS:
        issues.append(
            Issue(
                code="stale_fundamentals",
                message=(
                    f"Statements end {data.period.period_end} ({age} days before the price "
                    "date); multiples compare today's price with old fundamentals."
                ),
            )
        )
    events = share_count_events_after_period or []
    share_basis_broken = bool(events)
    if share_basis_broken:
        issues.append(
            Issue(
                code="share_count_changed_after_period",
                message="Share-count events after the period end: " + "; ".join(events),
            )
        )
    if data.period.fiscal_period.value != "FY":
        issues.append(
            Issue(
                code="non_annual_period",
                severity=IssueSeverity.WARNING,
                message="Multiples use a single quarter's flows; they are not annualized.",
            )
        )

    inc, bal = data.income, data.balance
    blocked_reason = (
        "share count/EPS are from before a split or bonus; not comparable with the current price"
    )

    m: dict[str, MetricResult] = {}
    shares = bal.shares_outstanding
    market_cap: Decimal | None = None
    if share_basis_broken:
        m["market_cap"] = _blocked(
            "Market capitalization", "currency", "price * shares_outstanding", blocked_reason
        )
    else:
        cap_units = price.price * shares if shares is not None else None
        market_cap = rescale(cap_units, Scale.UNITS, data.scale) if cap_units is not None else None
        m["market_cap"] = _amount(
            "Market capitalization",
            "price * shares_outstanding",
            {"price": price.price, "shares_outstanding": shares},
            market_cap,
        )

    debt = total_debt(data)
    cash = bal.cash_and_equivalents
    ev: Decimal | None = None
    if share_basis_broken:
        m["enterprise_value"] = _blocked(
            "Enterprise value",
            "currency",
            "market_cap + total_debt + minority_interest + preferred_equity - cash",
            blocked_reason,
        )
    else:
        omitted = [
            name
            for name, value in (
                ("minority_interest", bal.minority_interest),
                ("preferred_equity", bal.preferred_equity),
            )
            if value is None
        ]
        required = {"market_cap": market_cap, "total_debt": debt, "cash_and_equivalents": cash}
        if all(v is not None for v in required.values()):
            assert market_cap is not None and debt is not None and cash is not None  # noqa: S101
            ev = (
                market_cap
                + debt
                + (bal.minority_interest or Decimal(0))
                + (bal.preferred_equity or Decimal(0))
                - cash
            )
        # Minority interest / preferred are optional claims: only market cap, debt and cash gate.
        missing = [k for k, v in required.items() if v is None]
        m["enterprise_value"] = MetricResult(
            name="Enterprise value",
            value=ev,
            unit="currency",
            formula="market_cap + total_debt + minority_interest + preferred_equity - cash",
            inputs={
                **required,
                "minority_interest": bal.minority_interest,
                "preferred_equity": bal.preferred_equity,
            },
            status="missing_inputs" if missing else "ok",
            missing=missing,
            note=f"not reported, so not added: {', '.join(omitted)}" if omitted else None,
        )

    if share_basis_broken:
        m["price_to_earnings"] = _blocked("P/E", "times", "price / diluted_eps", blocked_reason)
        m["price_to_book"] = _blocked("P/B", "times", "market_cap / total_equity", blocked_reason)
        m["ev_to_ebitda"] = _blocked(
            "EV/EBITDA", "times", "enterprise_value / ebitda", blocked_reason
        )
        m["ev_to_revenue"] = _blocked(
            "EV/Revenue", "times", "enterprise_value / revenue", blocked_reason
        )
    else:
        m["price_to_earnings"] = _divide(
            "P/E",
            "price / diluted_eps",
            "times",
            ("price", price.price),
            ("diluted_eps", inc.diluted_eps),
            note="not meaningful when EPS is zero or negative (loss-making)",
        )
        m["price_to_book"] = _divide(
            "P/B",
            "market_cap / total_equity",
            "times",
            ("market_cap", market_cap),
            ("total_equity", bal.total_equity),
        )
        m["ev_to_ebitda"] = _divide(
            "EV/EBITDA",
            "enterprise_value / ebitda",
            "times",
            ("enterprise_value", ev),
            ("ebitda", ebitda(data)),
            note="not meaningful when EBITDA is zero or negative",
        )
        m["ev_to_revenue"] = _divide(
            "EV/Revenue",
            "enterprise_value / revenue",
            "times",
            ("enterprise_value", ev),
            ("revenue", inc.revenue),
        )

    m["dividend_yield"] = _divide(
        "Dividend yield",
        "trailing_dividends_per_share / price",
        "ratio",
        ("trailing_dividends_per_share", trailing_dividends_per_share),
        ("price", price.price),
        note=dividends_note,
    )

    return MarketMultiplesReport(
        company=data.company,
        period=data.period,
        price=price,
        currency=data.currency,
        scale=data.scale,
        metrics=m,
        issues=issues,
    )
