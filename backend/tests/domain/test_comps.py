from typing import Any

import pytest

from app.domain.comps import CompanyMetrics, Multiple, analyze_comps
from tests.domain.helpers import D, approx


def company(name: str, **fields: Any) -> CompanyMetrics:
    return CompanyMetrics.model_validate(
        {"company": name, "currency": "USD", "scale": "millions"} | fields
    )


TARGET = company(
    "TGT",
    market_cap=D(1000),
    net_debt=D(200),
    revenue=D(500),
    ebitda=D(100),
    net_income=D(50),
    book_equity=D(400),
    shares_outstanding=D(100),
)
PEERS = [
    # explicit EV
    company(
        "A",
        market_cap=D(1000),
        enterprise_value=D(1200),
        revenue=D(600),
        ebitda=D(120),
        net_income=D(60),
        book_equity=D(500),
    ),
    company(
        "B",
        market_cap=D(2000),
        net_debt=D(400),
        revenue=D(1000),
        ebitda=D(200),
        net_income=D(100),
        book_equity=D(800),
    ),
    # loss-making: excluded from P/E
    company(
        "C",
        market_cap=D(1500),
        net_debt=D(0),
        revenue=D(1000),
        ebitda=D(150),
        net_income=D(-10),
        book_equity=D(1000),
    ),
    # reported in thousands; no book equity
    company(
        "D",
        scale="thousands",
        market_cap=D(3_000_000),
        net_debt=D(0),
        revenue=D(1_500_000),
        ebitda=D(250_000),
        net_income=D(150_000),
    ),
]


@pytest.fixture
def result() -> Any:
    return analyze_comps(TARGET, PEERS)


def test_peer_multiples_with_rescaling(result: Any) -> None:
    ev_ebitda = result.stats[Multiple.EV_EBITDA]
    assert ev_ebitda.values == {"A": D(10), "B": D(12), "C": D(10), "D": D(12)}
    assert (ev_ebitda.minimum, ev_ebitda.p25, ev_ebitda.median, ev_ebitda.p75) == (
        D(10),
        D(10),
        D(11),
        D(12),
    )
    assert ev_ebitda.mean == D(11)
    assert result.stats[Multiple.EV_REVENUE].median == D(2)


def test_exclusions_are_explained(result: Any) -> None:
    pe = result.stats[Multiple.PRICE_EARNINGS]
    assert "C" not in pe.values
    assert pe.excluded["C"].startswith("non-positive net_income")
    pb = result.stats[Multiple.PRICE_BOOK]
    assert pb.excluded == {"D": "missing book_equity"}


def test_implied_ev_multiple_valuation(result: Any) -> None:
    v = result.implied[Multiple.EV_EBITDA]
    assert v.implied_enterprise_value == D(1100)  # 11 x 100
    assert v.implied_equity_value == D(900)  # 1100 - 200 net debt
    assert v.implied_value_per_share == D(9)
    assert (v.low_value_per_share, v.high_value_per_share) == (D(8), D(10))


def test_implied_equity_multiple_valuation(result: Any) -> None:
    v = result.implied[Multiple.PRICE_EARNINGS]
    assert v.implied_enterprise_value is None
    assert approx(v.implied_equity_value, 1000)  # median P/E 20 x 50
    assert approx(v.implied_value_per_share, 10)


def test_no_warnings_with_enough_peers(result: Any) -> None:
    assert result.warnings == []


def test_few_peers_warning() -> None:
    r = analyze_comps(TARGET, PEERS[:2], [Multiple.EV_EBITDA])
    assert [w.code for w in r.warnings] == ["few_peers"]


def test_target_excluded_from_its_own_peers() -> None:
    r = analyze_comps(TARGET, [*PEERS, TARGET], [Multiple.EV_EBITDA])
    assert r.stats[Multiple.EV_EBITDA].excluded["TGT"] == "target company"


def test_non_positive_target_metric_not_applicable() -> None:
    loss_target = TARGET.model_copy(update={"ebitda": D(-5)})
    v = analyze_comps(loss_target, PEERS).implied[Multiple.EV_EBITDA]
    assert v.implied_value_per_share is None
    assert "non-positive" in (v.note or "")


def test_missing_net_debt_blocks_ev_bridge() -> None:
    no_bridge = TARGET.model_copy(update={"net_debt": None})
    v = analyze_comps(no_bridge, PEERS).implied[Multiple.EV_EBITDA]
    assert v.implied_equity_value is None
    assert "net_debt" in (v.note or "")


def test_peer_without_ev_or_net_debt_is_excluded() -> None:
    r = analyze_comps(TARGET, [company("E", market_cap=D(10), ebitda=D(1))], [Multiple.EV_EBITDA])
    assert r.stats[Multiple.EV_EBITDA].excluded["E"] == "missing enterprise_value"
    assert r.implied[Multiple.EV_EBITDA].note == "no usable peer multiples"


def test_input_validation() -> None:
    with pytest.raises(ValueError, match="convert currencies"):
        analyze_comps(TARGET, [company("EU", currency="EUR", market_cap=D(1))])
    with pytest.raises(ValueError, match="at least one peer"):
        analyze_comps(TARGET, [])
    with pytest.raises(ValueError, match="duplicate"):
        analyze_comps(TARGET, [PEERS[0], PEERS[0]])
