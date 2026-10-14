"""SYNTHETIC SEC companyfacts document for tests.

Shaped like https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json, but every number
here is made up and belongs to a fictional company ("Synthetic Widgets Inc."). It exercises:
- two annual 10-K filings, each also carrying prior-year comparatives;
- a restatement (FY2023 revenue 880 originally, 900 in the FY2024 10-K -> 900 must win);
- a 3-month Q4 duration inside a 10-K and a 10-Q fact (both must be ignored);
- a lower-priority revenue concept that must not override the preferred one;
- a negative capex value that violates the domain sign convention (must be dropped);
- an FY2022 comparative-only period that must not become its own fiscal period.
"""

from typing import Any

CIK = "0000000042"
ACC_2024 = "0000000042-24-000010"
ACC_2023 = "0000000042-23-000010"
FY24 = ("2023-10-01", "2024-09-28")
FY23 = ("2022-10-02", "2023-09-30")
FY22 = ("2021-09-26", "2022-10-01")


def _f(
    val: float | int,
    period: tuple[str, str] | str,
    accn: str,
    fy: int,
    filed: str,
    form: str = "10-K",
    fp: str = "FY",
) -> dict[str, Any]:
    fact: dict[str, Any] = {"val": val, "accn": accn, "fy": fy, "fp": fp, "form": form}
    fact["filed"] = filed
    if isinstance(period, tuple):
        fact["start"], fact["end"] = period
    else:
        fact["end"] = period
    return fact


def _both(cur24: float | int, cur23: float | int, instant: bool = False) -> list[dict[str, Any]]:
    """Values reported in both 10-Ks (FY2024 10-K repeats FY2023 as a comparative)."""
    p24: tuple[str, str] | str = FY24[1] if instant else FY24
    p23: tuple[str, str] | str = FY23[1] if instant else FY23
    return [
        _f(cur24, p24, ACC_2024, 2024, "2024-11-01"),
        _f(cur23, p23, ACC_2024, 2024, "2024-11-01"),
        _f(cur23, p23, ACC_2023, 2023, "2023-11-03"),
    ]


def _usd(entries: list[dict[str, Any]], unit: str = "USD") -> dict[str, Any]:
    return {"label": "synthetic", "units": {unit: entries}}


def companyfacts() -> dict[str, Any]:
    revenue = [
        _f(1000, FY24, ACC_2024, 2024, "2024-11-01"),
        _f(900, FY23, ACC_2024, 2024, "2024-11-01"),  # restated comparative
        _f(800, FY22, ACC_2024, 2024, "2024-11-01"),
        _f(880, FY23, ACC_2023, 2023, "2023-11-03"),  # original
        _f(800, FY22, ACC_2023, 2023, "2023-11-03"),
        _f(300, ("2024-06-30", "2024-09-28"), ACC_2024, 2024, "2024-11-01"),  # Q4 only
        _f(
            250,
            ("2023-10-01", "2023-12-30"),
            "0000000042-24-000001",
            2024,
            "2024-02-01",
            "10-Q",
            "Q1",
        ),
    ]
    return {
        "cik": 42,
        "entityName": "Synthetic Widgets Inc.",
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": _usd(revenue),
                "SalesRevenueNet": _usd([_f(999, FY24, ACC_2024, 2024, "2024-11-01")]),
                "CostOfRevenue": _usd(_both(600, 540)),
                "OperatingIncomeLoss": _usd(_both(200, 180)),
                "NetIncomeLoss": _usd(_both(150, 120)),
                "Assets": _usd(_both(2000, 1800, instant=True)),
                "StockholdersEquity": _usd(_both(900, 800, instant=True)),
                "CashAndCashEquivalentsAtCarryingValue": _usd(_both(100, 90, instant=True)),
                "NetCashProvidedByUsedInOperatingActivities": _usd(_both(250, 220)),
                "PaymentsToAcquirePropertyPlantAndEquipment": _usd(_both(80, -5)),
                "CommonStockSharesOutstanding": _usd(
                    [_f(100, FY24[1], ACC_2024, 2024, "2024-11-01")], "shares"
                ),
                "EarningsPerShareDiluted": _usd(
                    [_f(1.5, FY24, ACC_2024, 2024, "2024-11-01")], "USD/shares"
                ),
            },
            "dei": {},
        },
    }
