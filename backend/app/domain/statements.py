"""Normalized financial statements for one company and one reporting period.

Sign conventions (the ingestion layer must normalize provider data to these):
- Revenue, profits and cash flows: natural sign (losses are negative).
- ``interest_expense``, ``capital_expenditures``, ``dividends_paid``, ``share_repurchases``:
  positive magnitudes of money spent.
- Balance-sheet assets and liabilities: non-negative. ``total_equity`` may be negative.

Every field is optional: ``None`` means "not reported / not available" and is never treated as 0.
"""

from typing import Annotated

from pydantic import Field

from app.domain.types import (
    Amount,
    CurrencyCode,
    DomainModel,
    ReportingPeriod,
    Scale,
    SourceRef,
    ValueKind,
)

NonNegative = Annotated[Amount, Field(ge=0)]
Positive = Annotated[Amount, Field(gt=0)]


class IncomeStatement(DomainModel):
    revenue: Amount | None = None
    cost_of_revenue: NonNegative | None = None
    gross_profit: Amount | None = None
    operating_income: Amount | None = None  # EBIT
    depreciation_amortization: NonNegative | None = None
    interest_expense: NonNegative | None = None
    pretax_income: Amount | None = None
    income_tax_expense: Amount | None = None
    net_income: Amount | None = None  # attributable to common shareholders
    diluted_shares: Positive | None = None
    diluted_eps: Amount | None = None


class BalanceSheet(DomainModel):
    cash_and_equivalents: NonNegative | None = None
    short_term_investments: NonNegative | None = None
    accounts_receivable: NonNegative | None = None
    inventory: NonNegative | None = None
    total_current_assets: NonNegative | None = None
    total_assets: NonNegative | None = None
    accounts_payable: NonNegative | None = None
    total_current_liabilities: NonNegative | None = None
    short_term_debt: NonNegative | None = None
    long_term_debt: NonNegative | None = None
    total_debt: NonNegative | None = None  # if reported directly; else derived from components
    total_liabilities: NonNegative | None = None
    total_equity: Amount | None = None
    minority_interest: NonNegative | None = None
    preferred_equity: NonNegative | None = None
    shares_outstanding: Positive | None = None


class CashFlowStatement(DomainModel):
    operating_cash_flow: Amount | None = None
    capital_expenditures: NonNegative | None = None
    dividends_paid: NonNegative | None = None
    share_repurchases: NonNegative | None = None


class FinancialPeriodData(DomainModel):
    """All statements for one company-period, sharing one currency and scale."""

    company: str = Field(min_length=1, max_length=50)  # ticker or internal ID
    period: ReportingPeriod
    currency: CurrencyCode
    scale: Scale
    source: SourceRef
    kind: ValueKind = ValueKind.REPORTED
    income: IncomeStatement = IncomeStatement()
    balance: BalanceSheet = BalanceSheet()
    cash_flow: CashFlowStatement = CashFlowStatement()
