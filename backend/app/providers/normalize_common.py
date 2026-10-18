"""Helpers shared by provider normalizers (pure, no I/O)."""

from pydantic import BaseModel, ValidationError

from app.domain.statements import BalanceSheet, CashFlowStatement, IncomeStatement
from app.providers.base import IngestedLineItem, StatementName

STATEMENT_MODELS: dict[StatementName, type[BaseModel]] = {
    "income": IncomeStatement,
    "balance": BalanceSheet,
    "cash_flow": CashFlowStatement,
}


def validate_statement_items(
    statement: StatementName,
    items: list[IngestedLineItem],
    label: str,
    warnings: list[str],
) -> list[IngestedLineItem]:
    """Drop items that the domain model rejects (e.g. negative capex), with a warning."""
    model = STATEMENT_MODELS[statement]
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
