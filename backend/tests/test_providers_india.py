"""Indian-market providers: Tej (MockTransport), yfinance normalizer/adapter, demo, cache.
No test touches the network."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from app.core.cache import TTLCache
from app.providers import yfinance_fundamentals
from app.providers.base import (
    CapabilityUnavailableError,
    InstrumentRef,
    ProviderError,
    ProviderNotFoundError,
    ProviderRateLimitedError,
)
from app.providers.demo import DemoMarketDataProvider
from app.providers.tej import TejMarketDataProvider, parse_snapshot
from app.providers.yfinance_normalize import (
    BASIS_WARNING,
    fiscal_label,
    normalize_yahoo_statements,
)
from tests import fixtures_india as fx

# --- Tej ------------------------------------------------------------------------------------------


def tej(handler: Any, sleeps: list[float] | None = None) -> TejMarketDataProvider:
    return TejMarketDataProvider(
        transport=httpx.MockTransport(handler),
        sleep=(sleeps.append if sleeps is not None else lambda _: None),
    )


class Routes:
    """MockTransport handler: path(+query) prefix -> JSON body; anything else is a 404."""

    def __init__(self, table: dict[str, Any]) -> None:
        self.table = table
        self.calls: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(str(request.url))
        query = request.url.query.decode()
        key = request.url.path + (f"?{query}" if query else "")
        for prefix, body in self.table.items():
            if key.startswith(prefix):
                return httpx.Response(200, json=body)
        return httpx.Response(404, json={"error": "not_found"})


def test_tej_directory_uses_latest_published_trading_date() -> None:
    handler = Routes(
        {
            "/v1/status": fx.STATUS,
            f"/v1/snapshot/nse?date={fx.TRADING_DATE}": fx.SNAPSHOT_NSE,
            f"/v1/snapshot/bse?date={fx.TRADING_DATE}": fx.SNAPSHOT_BSE,
        }
    )
    result = tej(handler).fetch_directory()
    assert result.as_of == date(2026, 10, 16)
    by_key = {(x.exchange, x.symbol): x for x in result.listings}
    assert set(by_key) == {
        ("NSE", "ALPHA"),
        ("NSE", "BETA"),
        ("NSE", "M&M"),
        ("NSE", "NOISIN"),
        ("BSE", "ALPHA"),
        ("BSE", "BETA"),
    }  # the row without a symbol is skipped
    assert by_key[("NSE", "ALPHA")].company_key == by_key[("BSE", "ALPHA")].company_key
    assert by_key[("NSE", "BETA")].company_key != by_key[("BSE", "BETA")].company_key
    noisin = by_key[("NSE", "NOISIN")]
    assert noisin.isin is None and noisin.company_key == "NSE:NOISIN"  # malformed ISIN dropped
    assert by_key[("BSE", "ALPHA")].series == "A"
    assert all(x.last_traded_on == date(2026, 10, 16) for x in result.listings)


def test_tej_bars_are_validated_and_unadjusted() -> None:
    handler = Routes({"/v1/ohlcv/nse/ALPHA?from=2026-10-12&to=2026-10-16": fx.OHLCV})
    series = tej(handler).fetch_eod_bars("NSE", "alpha", date(2026, 10, 12), date(2026, 10, 16))
    assert [b.date for b in series.bars] == [date(2026, 10, 14), date(2026, 10, 16)]
    assert series.warnings == ["dropped 1 malformed or inconsistent price rows"]
    last = series.bars[-1]
    assert (last.close, last.prev_close, last.volume) == (
        Decimal("1025.5"),
        Decimal("1010.0"),
        2000000,
    )
    assert series.nature == "end_of_day" and series.adjusted is False and series.currency == "INR"


def test_tej_actions_parse_types() -> None:
    actions = tej(Routes({"/v1/actions/ALPHA": fx.ACTIONS})).fetch_corporate_actions("ALPHA")
    kinds = [(a.exchange, a.action_type, str(a.ex_date)) for a in actions.actions]
    assert kinds[0][1] == "dividend"
    assert ("NSE", "other", "2023-07-20") in kinds  # unknown type is "other", not guessed
    bonus = next(a for a in actions.actions if a.action_type == "bonus")
    assert (bonus.ratio_numerator, bonus.ratio_denominator) == (1, 1)
    assert next(a for a in actions.actions if a.action_type == "dividend").cash_amount == 6


def test_tej_invalid_symbol_is_rejected_locally() -> None:
    handler = Routes({})
    with pytest.raises(ProviderNotFoundError):
        tej(handler).fetch_eod_bars("NSE", "bad symbol!", date(2026, 1, 1), date(2026, 1, 2))
    assert handler.calls == []


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (404, ProviderNotFoundError),
        (400, ProviderNotFoundError),
        (402, CapabilityUnavailableError),
        (401, CapabilityUnavailableError),
        (418, ProviderError),
    ],
)
def test_tej_status_mapping(status: int, error: type[Exception]) -> None:
    provider = tej(lambda _: httpx.Response(status, json={"error": "x"}))
    with pytest.raises(error):
        provider.fetch_corporate_actions("ALPHA")


def test_tej_retries_rate_limits_then_gives_up() -> None:
    sleeps: list[float] = []
    attempts = {"n": 0}

    def flaky(_: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] < 3:
            return httpx.Response(429, headers={"Retry-After": "2"})
        return httpx.Response(200, json=fx.ACTIONS)

    assert tej(flaky, sleeps).fetch_corporate_actions("ALPHA").actions
    assert sleeps == [2.0, 2.0]

    with pytest.raises(ProviderRateLimitedError):
        tej(lambda _: httpx.Response(429), []).fetch_corporate_actions("ALPHA")


def test_tej_malformed_payloads() -> None:
    with pytest.raises(ProviderError, match="malformed"):
        tej(lambda _: httpx.Response(200, content=b"<html>")).fetch_corporate_actions("ALPHA")
    with pytest.raises(ProviderError, match="envelope"):
        tej(lambda _: httpx.Response(200, json=[1, 2])).fetch_corporate_actions("ALPHA")
    with pytest.raises(ProviderError):
        parse_snapshot("NSE", {"not": "a list"}, date(2026, 1, 1))


def test_tej_status_failure_is_reported_not_raised() -> None:
    status = tej(lambda _: httpx.Response(503), []).status()
    assert status.reachable is False and status.latest_trading_date is None
    with pytest.raises(ProviderError):
        tej(lambda _: httpx.Response(503), []).fetch_directory()


# --- yfinance -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("end", "expected"),
    [
        (date(2026, 6, 30), (2027, "Q1")),
        (date(2026, 9, 30), (2027, "Q2")),
        (date(2025, 12, 31), (2026, "Q3")),
        (date(2026, 3, 31), (2026, "Q4")),
        (date(2025, 11, 30), None),
    ],
)
def test_indian_fiscal_quarter_labels(end: date, expected: tuple[int, str] | None) -> None:
    assert fiscal_label(end, fy_end_month=3) == expected


def test_yahoo_normalization() -> None:
    result = normalize_yahoo_statements(fx.YAHOO_TABLES, currency="INR")
    labels = [(p.fiscal_year, p.fiscal_period, str(p.period_end)) for p in result.periods]
    assert labels == [
        (2026, "FY", "2026-03-31"),
        (2025, "FY", "2025-03-31"),
        (2027, "Q1", "2026-06-30"),
        (2026, "Q4", "2026-03-31"),
        (2026, "Q3", "2025-12-31"),
    ]
    assert {(p.currency, p.scale, p.basis) for p in result.periods} == {
        ("INR", "units", "unspecified")
    }
    fy26 = {f"{i.statement}.{i.item}": i for i in result.periods[0].items}
    assert fy26["income.revenue"].value == Decimal("10000000000000.0")
    assert fy26["income.revenue"].source_concept == "yfinance:Total Revenue"
    assert fy26["income.diluted_eps"].value == Decimal("59.25")  # per share: unscaled
    assert fy26["cash_flow.capital_expenditures"].value == Decimal("1200000000000.0")  # negated
    assert fy26["cash_flow.dividends_paid"].value == Decimal("75000000000.0")
    assert "balance.inventory" not in fy26  # NaN stays missing
    fy25 = {f"{i.statement}.{i.item}" for i in result.periods[1].items}
    assert "income.net_income" in fy25  # fallback label "Net Income"
    assert "cash_flow.capital_expenditures" not in fy25  # positive capex dropped
    assert result.warnings[0] == BASIS_WARNING
    assert any("capital_expenditures" in w for w in result.warnings)
    assert any("2025-11-30" in w and "not aligned" in w for w in result.warnings)


def test_yahoo_quarters_need_annual_data() -> None:
    result = normalize_yahoo_statements({"quarterly": fx.YAHOO_TABLES["quarterly"]}, currency="INR")
    assert result.periods == []
    assert any("no annual data" in w for w in result.warnings)


class _Frame:
    """Minimal stand-in for a pandas DataFrame (columns of {label: value})."""

    def __init__(self, table: dict[str, dict[str, Any]]) -> None:
        self._table = table
        self.empty = not table
        self.columns = [SimpleNamespace(date=lambda d=d: date.fromisoformat(d)) for d in table]

    def __getitem__(self, column: Any) -> Any:
        return SimpleNamespace(items=self._table[column.date().isoformat()].items)


def _fake_yfinance(monkeypatch: pytest.MonkeyPatch, ticker: Any) -> list[str]:
    requested: list[str] = []

    def make(symbol: str) -> Any:
        requested.append(symbol)
        return ticker() if callable(ticker) else ticker

    monkeypatch.setattr(yfinance_fundamentals, "yfinance_available", lambda: True)
    monkeypatch.setattr(
        yfinance_fundamentals.importlib, "import_module", lambda _: SimpleNamespace(Ticker=make)
    )
    return requested


def test_yfinance_adapter_maps_symbols_and_frames(monkeypatch: pytest.MonkeyPatch) -> None:
    tables = fx.YAHOO_TABLES
    ticker = SimpleNamespace(
        income_stmt=_Frame(tables["annual"]["income"]),
        balance_sheet=_Frame(tables["annual"]["balance"]),
        cashflow=_Frame(tables["annual"]["cash_flow"]),
        quarterly_income_stmt=_Frame(tables["quarterly"]["income"]),
        quarterly_balance_sheet=_Frame({}),
        quarterly_cashflow=_Frame({}),
        info={"financialCurrency": "INR"},
    )
    requested = _fake_yfinance(monkeypatch, ticker)
    provider = yfinance_fundamentals.YFinanceFundamentalsProvider()
    result = provider.fetch_financials(InstrumentRef("NSE", "M&M", None, "x"))
    assert requested == ["M&M.NS"]
    assert result.provider == "yfinance" and len(result.periods) == 5
    assert result.source_url == "https://finance.yahoo.com/quote/M&M.NS/financials"
    provider.fetch_financials(InstrumentRef("BSE", "ALPHA", None, "x"))
    assert requested[-1] == "ALPHA.BO"


def test_yfinance_adapter_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    class YFRateLimitError(Exception):
        pass

    def limited() -> Any:
        raise YFRateLimitError("Too Many Requests")

    ref = InstrumentRef("NSE", "ALPHA", None, "x")
    _fake_yfinance(monkeypatch, limited)
    with pytest.raises(ProviderRateLimitedError):
        yfinance_fundamentals.YFinanceFundamentalsProvider().fetch_financials(ref)

    frames = [attr for table in yfinance_fundamentals._FRAMES.values() for attr in table.values()]
    empty = SimpleNamespace(**{attr: _Frame({}) for attr in frames}, info={})
    _fake_yfinance(monkeypatch, empty)
    with pytest.raises(ProviderNotFoundError):
        yfinance_fundamentals.YFinanceFundamentalsProvider().fetch_financials(ref)


def test_yfinance_missing_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(yfinance_fundamentals, "yfinance_available", lambda: False)
    with pytest.raises(RuntimeError, match="not installed"):
        yfinance_fundamentals.YFinanceFundamentalsProvider()


# --- demo -----------------------------------------------------------------------------------------

TODAY = date(2026, 10, 18)  # a Sunday


def test_demo_is_deterministic_and_labelled() -> None:
    a, b = DemoMarketDataProvider(lambda: TODAY), DemoMarketDataProvider(lambda: TODAY)
    span = (date(2026, 9, 1), date(2026, 10, 18))
    assert a.fetch_eod_bars("NSE", "DEMOINFO", *span) == b.fetch_eod_bars("NSE", "DEMOINFO", *span)
    ref = InstrumentRef("NSE", "DEMOINFO", None, "x")
    assert a.fetch_financials(ref).periods == b.fetch_financials(ref).periods

    series = a.fetch_eod_bars("NSE", "DEMOINFO", *span)
    assert series.nature == "demo" and series.provider == "demo"
    assert series.bars[-1].date == date(2026, 10, 16)  # Friday: last published weekday
    assert all(bar.date.weekday() < 5 for bar in series.bars)
    assert all(bar.low <= min(bar.open, bar.close) for bar in series.bars)
    assert all(max(bar.open, bar.close) <= bar.high for bar in series.bars)
    # A day's price does not depend on the requested window.
    single = a.fetch_eod_bars("NSE", "DEMOINFO", date(2026, 10, 16), date(2026, 10, 16))
    assert single.bars[0] == series.bars[-1]


def test_demo_directory_never_invents_isins() -> None:
    listings = DemoMarketDataProvider(lambda: TODAY).fetch_directory().listings
    assert all(x.isin is None for x in listings)
    assert all(x.name.startswith("Demo") for x in listings)
    keys = {(x.exchange, x.symbol): x.company_key for x in listings}
    assert keys[("NSE", "DEMOINFO")] == keys[("BSE", "DEMOINFO")]
    assert keys[("NSE", "DEMOAGRO")] != keys[("BSE", "DEMOAGRO")]


def test_demo_financials_cover_bases_and_periods() -> None:
    demo = DemoMarketDataProvider(lambda: TODAY)
    result = demo.fetch_financials(InstrumentRef("NSE", "DEMOINFO", None, "x"))
    periods = {(p.basis, p.fiscal_year, p.fiscal_period) for p in result.periods}
    assert ("consolidated", 2026, "FY") in periods and ("standalone", 2026, "FY") in periods
    assert ("consolidated", 2027, "Q1") in periods  # Apr-Jun 2026 quarter
    assert ("consolidated", 2027, "Q2") not in periods  # Sep quarter not yet reported
    assert {(p.currency, p.scale) for p in result.periods} == {("INR", "crores")}
    with pytest.raises(ProviderNotFoundError):
        demo.fetch_eod_bars("BSE", "DEMOSTEEL", date(2026, 1, 1), date(2026, 1, 2))


# --- cache ----------------------------------------------------------------------------------------


def test_ttl_cache_expiry_eviction_and_errors() -> None:
    now = {"t": 0.0}
    cache = TTLCache(10, max_entries=2, clock=lambda: now["t"])

    assert cache.get_or_load("a", lambda: "a") == ("a", False)
    assert cache.get_or_load("a", lambda: "a2") == ("a", True)
    now["t"] = 11
    assert cache.get_or_load("a", lambda: "a3") == ("a3", False)  # expired
    cache.get_or_load("b", lambda: "b")
    cache.get_or_load("c", lambda: "c")  # evicts the least recently used ("a")
    assert cache.get_or_load("a", lambda: "a4") == ("a4", False)

    def boom() -> str:
        raise ProviderError("down")

    with pytest.raises(ProviderError):
        cache.get_or_load("x", boom)
    assert cache.get_or_load("x", lambda: "x") == ("x", False)  # failures are not cached

    disabled = TTLCache(0)
    disabled.get_or_load("k", lambda: "k1")
    assert disabled.get_or_load("k", lambda: "k2") == ("k2", False)
