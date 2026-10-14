"""Normalize SEC EDGAR XBRL "companyfacts" JSON into annual statement line items.

Pure function, no I/O. Rules:

1. Only US-GAAP facts from annual reports are used: ``form`` in {10-K, 10-K/A} and
   ``fp == "FY"``. Foreign filers (20-F / IFRS) are not supported yet.
2. Fiscal periods: for each filing (accession), its fiscal period ends on the latest ``end``
   among its full-year duration facts; that period gets the filing's ``fy``. This avoids
   mislabelling the prior-year comparatives that every 10-K also contains.
3. Duration items (income statement, cash flow) must span 350-380 days (52/53-week years);
   instant items (balance sheet) are taken at the period-end date.
4. Each field maps to an ordered list of concepts; the first concept with a value for that
   period wins, and the concept used is recorded. If a value was reported in several filings
   (restatements), the most recently filed one wins and its accession is recorded.
5. Values are passed through the domain statement models; values violating domain sign
   conventions are dropped with a warning rather than coerced.
6. Nothing is derived or estimated here; absent concepts simply produce absent fields.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, ValidationError

from app.domain.statements import BalanceSheet, CashFlowStatement, IncomeStatement
from app.providers.base import IngestedLineItem, IngestedPeriod, StatementName

ANNUAL_FORMS = frozenset({"10-K", "10-K/A"})
MIN_YEAR_DAYS, MAX_YEAR_DAYS = 350, 380


@dataclass(frozen=True)
class FieldMapping:
    statement: StatementName
    item: str
    concepts: tuple[str, ...]
    unit: str = "USD"


MAPPINGS: tuple[FieldMapping, ...] = (
    # --- income statement (duration) ---
    FieldMapping(
        "income",
        "revenue",
        (
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "Revenues",
            "SalesRevenueNet",
            "RevenueFromContractWithCustomerIncludingAssessedTax",
        ),
    ),
    FieldMapping(
        "income",
        "cost_of_revenue",
        ("CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold"),
    ),
    FieldMapping("income", "gross_profit", ("GrossProfit",)),
    FieldMapping("income", "operating_income", ("OperatingIncomeLoss",)),
    FieldMapping(
        "income",
        "depreciation_amortization",
        ("DepreciationDepletionAndAmortization", "DepreciationAndAmortization"),
    ),
    FieldMapping("income", "interest_expense", ("InterestExpense",)),
    FieldMapping(
        "income",
        "pretax_income",
        (
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
        ),
    ),
    FieldMapping("income", "income_tax_expense", ("IncomeTaxExpenseBenefit",)),
    FieldMapping("income", "net_income", ("NetIncomeLoss",)),
    FieldMapping(
        "income", "diluted_shares", ("WeightedAverageNumberOfDilutedSharesOutstanding",), "shares"
    ),
    FieldMapping("income", "diluted_eps", ("EarningsPerShareDiluted",), "USD/shares"),
    # --- balance sheet (instant) ---
    FieldMapping("balance", "cash_and_equivalents", ("CashAndCashEquivalentsAtCarryingValue",)),
    FieldMapping(
        "balance", "short_term_investments", ("ShortTermInvestments", "MarketableSecuritiesCurrent")
    ),
    FieldMapping("balance", "accounts_receivable", ("AccountsReceivableNetCurrent",)),
    FieldMapping("balance", "inventory", ("InventoryNet",)),
    FieldMapping("balance", "total_current_assets", ("AssetsCurrent",)),
    FieldMapping("balance", "total_assets", ("Assets",)),
    FieldMapping("balance", "accounts_payable", ("AccountsPayableCurrent",)),
    FieldMapping("balance", "total_current_liabilities", ("LiabilitiesCurrent",)),
    FieldMapping("balance", "short_term_debt", ("DebtCurrent",)),
    FieldMapping("balance", "long_term_debt", ("LongTermDebtNoncurrent",)),
    FieldMapping("balance", "total_liabilities", ("Liabilities",)),
    FieldMapping("balance", "total_equity", ("StockholdersEquity",)),
    FieldMapping("balance", "minority_interest", ("MinorityInterest",)),
    FieldMapping("balance", "shares_outstanding", ("CommonStockSharesOutstanding",), "shares"),
    # --- cash flow statement (duration) ---
    FieldMapping(
        "cash_flow", "operating_cash_flow", ("NetCashProvidedByUsedInOperatingActivities",)
    ),
    FieldMapping(
        "cash_flow", "capital_expenditures", ("PaymentsToAcquirePropertyPlantAndEquipment",)
    ),
    FieldMapping(
        "cash_flow", "dividends_paid", ("PaymentsOfDividends", "PaymentsOfDividendsCommonStock")
    ),
    FieldMapping("cash_flow", "share_repurchases", ("PaymentsForRepurchaseOfCommonStock",)),
)

_STATEMENT_MODELS: dict[StatementName, type[BaseModel]] = {
    "income": IncomeStatement,
    "balance": BalanceSheet,
    "cash_flow": CashFlowStatement,
}
_INSTANT_STATEMENTS: frozenset[StatementName] = frozenset({"balance"})


@dataclass(frozen=True)
class _Fact:
    start: date | None
    end: date
    value: Decimal
    accession: str | None
    filed: str
    fy: int | None


@dataclass(frozen=True)
class NormalizedFinancials:
    entity_name: str | None
    periods: list[IngestedPeriod]
    warnings: list[str]


def _parse_date(raw: Any) -> date | None:
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        return None


def _annual_facts(entries: list[dict[str, Any]]) -> list[_Fact]:
    out: list[_Fact] = []
    for e in entries:
        if e.get("form") not in ANNUAL_FORMS or e.get("fp") != "FY":
            continue
        end = _parse_date(e.get("end"))
        if end is None or e.get("val") is None:
            continue
        try:
            value = Decimal(str(e["val"]))
        except InvalidOperation:
            continue
        if not value.is_finite():
            continue
        fy = e.get("fy")
        out.append(
            _Fact(
                start=_parse_date(e["start"]) if e.get("start") else None,
                end=end,
                value=value,
                accession=e.get("accn"),
                filed=str(e.get("filed", "")),
                fy=fy if isinstance(fy, int) else None,
            )
        )
    return out


def _is_full_year(fact: _Fact) -> bool:
    return fact.start is not None and MIN_YEAR_DAYS <= (fact.end - fact.start).days <= MAX_YEAR_DAYS


def _discover_periods(gaap: dict[str, Any]) -> dict[date, tuple[int, date | None]]:
    """period_end -> (fiscal_year, period_start), using each filing's latest full-year end."""
    by_accession: dict[str, list[_Fact]] = defaultdict(list)
    for concept in gaap.values():
        for entries in (concept.get("units") or {}).values():
            for fact in _annual_facts(entries):
                if _is_full_year(fact) and fact.accession and fact.fy is not None:
                    by_accession[fact.accession].append(fact)

    periods: dict[date, tuple[int, date | None, str]] = {}  # end -> (fy, start, filed)
    for facts in by_accession.values():
        period_end = max(f.end for f in facts)
        current = [f for f in facts if f.end == period_end]
        fy = current[0].fy
        assert fy is not None  # noqa: S101 - filtered above
        starts = [f.start for f in current if f.start is not None]
        start = max(set(starts), key=starts.count) if starts else None
        filed = max(f.filed for f in current)
        existing = periods.get(period_end)
        if existing is None or filed > existing[2]:
            periods[period_end] = (fy, start, filed)
    return {end: (fy, start) for end, (fy, start, _) in periods.items()}


def _value_for(
    gaap: dict[str, Any], mapping: FieldMapping, period_end: date
) -> tuple[_Fact, str] | None:
    instant = mapping.statement in _INSTANT_STATEMENTS
    for concept in mapping.concepts:
        entries = ((gaap.get(concept) or {}).get("units") or {}).get(mapping.unit)
        if not entries:
            continue
        candidates = [
            f
            for f in _annual_facts(entries)
            if f.end == period_end and (f.start is None if instant else _is_full_year(f))
        ]
        if candidates:
            return max(candidates, key=lambda f: f.filed), concept
    return None


def _validate_statement(
    statement: StatementName,
    items: list[IngestedLineItem],
    label: str,
    warnings: list[str],
) -> list[IngestedLineItem]:
    """Drop items that the domain model rejects (e.g. negative capex), with a warning."""
    model = _STATEMENT_MODELS[statement]
    kept = {i.item: i for i in items}
    for _ in range(len(items) + 1):
        try:
            model.model_validate({k: v.value for k, v in kept.items()})
            return list(kept.values())
        except ValidationError as exc:
            bad = {str(err["loc"][0]) for err in exc.errors() if err["loc"]}
            for name in bad & kept.keys():
                warnings.append(
                    f"{label}: dropped {statement}.{name}={kept[name].value} "
                    f"({kept[name].source_concept}) - violates domain constraints"
                )
                del kept[name]
            if not bad & kept.keys() and bad:
                break
    return list(kept.values())


def normalize_companyfacts(doc: dict[str, Any], *, max_years: int = 10) -> NormalizedFinancials:
    gaap: dict[str, Any] = (doc.get("facts") or {}).get("us-gaap") or {}
    warnings: list[str] = []
    if not gaap:
        return NormalizedFinancials(doc.get("entityName"), [], ["no us-gaap facts in document"])

    discovered = _discover_periods(gaap)
    periods: list[IngestedPeriod] = []
    for period_end in sorted(discovered, reverse=True)[:max_years]:
        fiscal_year, period_start = discovered[period_end]
        label = f"FY{fiscal_year}"
        by_statement: dict[StatementName, list[IngestedLineItem]] = defaultdict(list)
        for mapping in MAPPINGS:
            found = _value_for(gaap, mapping, period_end)
            if found is None:
                continue
            fact, concept = found
            by_statement[mapping.statement].append(
                IngestedLineItem(
                    statement=mapping.statement,
                    item=mapping.item,
                    value=fact.value,
                    source_concept=f"us-gaap:{concept}",
                    source_accession=fact.accession,
                )
            )
        items: list[IngestedLineItem] = []
        for statement, statement_items in by_statement.items():
            items.extend(_validate_statement(statement, statement_items, label, warnings))
        if not items:
            continue
        periods.append(
            IngestedPeriod(
                fiscal_year=fiscal_year,
                fiscal_period="FY",
                period_start=period_start,
                period_end=period_end,
                currency="USD",
                scale="units",
                items=items,
            )
        )

    seen_years: set[int] = set()
    unique: list[IngestedPeriod] = []
    for period in periods:  # newest first; a fiscal year can only appear once
        if period.fiscal_year in seen_years:
            warnings.append(
                f"FY{period.fiscal_year}: multiple period ends; kept latest, "
                f"skipped {period.period_end}"
            )
            continue
        seen_years.add(period.fiscal_year)
        unique.append(period)
    return NormalizedFinancials(doc.get("entityName"), unique, warnings)
