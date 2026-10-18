"""AI research Q&A: assemble citable sources, ask the model, verify every citation.

Sources are only (a) passages retrieved from the asking user's own uploaded reports and
(b) FinSight's stored figures for the company, each labelled with provider, period, basis,
currency, unit and provenance class. With no sources the model is not called at all.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.base import AIError, BlockMeta, LLMAnswer, LLMProvider, Source
from app.ai.grounding import GroundedAnswer, ground_answer
from app.ai.retrieval import Candidate, bm25
from app.core.errors import AppError
from app.domain.types import Scale, rescale
from app.models import Company, Document, DocumentChunk, User
from app.services import companies as company_service
from app.services.documents import ai_failure

STATEMENT_LABELS = {
    "revenue": "Revenue",
    "operating_income": "Operating profit (EBIT)",
    "net_income": "Net profit",
    "diluted_eps": "Diluted EPS",
    "total_assets": "Total assets",
    "total_equity": "Shareholders' equity",
    "total_debt": "Total debt",
    "cash_and_equivalents": "Cash and cash equivalents",
    "operating_cash_flow": "Operating cash flow",
    "capital_expenditures": "Capital expenditure",
}
PER_SHARE = {"diluted_eps"}
RATIO_KEYS = (
    "revenue_growth",
    "net_margin",
    "operating_margin",
    "return_on_equity",
    "return_on_capital_employed",
    "debt_to_equity",
    "interest_coverage",
)


def _amount_crore(value: Decimal, scale: str) -> str:
    crores = rescale(value, Scale(scale), Scale.CRORES)
    return f"₹{crores:,.2f} crore"


def financial_data_source(db: Session, company: Company) -> Source | None:
    """FinSight's stored figures for the latest two fiscal years of one basis, plus ratios."""
    try:
        basis = company_service.choose_basis(db, company, None)
    except AppError:
        return None
    by_year = company_service.annual_periods(db, company, basis)
    blocks: list[str] = []
    meta: list[BlockMeta] = []
    for year in sorted(by_year, reverse=True)[:2]:
        period = by_year[year]
        values = {i.item: Decimal(i.value) for i in period.line_items}
        for item, value in sorted(values.items()):
            label = STATEMENT_LABELS.get(item)
            if label is None:
                continue
            shown = (
                f"₹{value:,.2f} per share"
                if item in PER_SHARE
                else _amount_crore(value, period.scale)
            )
            text = (
                f"{label}, FY{year} ({period.period_end}), {basis}: {shown}. Reported; "
                f"source {period.source_provider}, retrieved {period.retrieved_at:%Y-%m-%d}."
            )
            blocks.append(text)
            meta.append(BlockMeta(label=f"{label} FY{year} ({basis}, reported)"))
    try:
        report = company_service.ratios(db, company, None, basis)
    except AppError:
        report = None
    if report is not None:
        for key in RATIO_KEYS:
            metric = report.metrics.get(key)
            if metric is None or metric.status != "ok" or metric.value is None:
                continue
            shown = (
                f"{metric.value * 100:.1f}%" if metric.unit == "ratio" else f"{metric.value:.2f}x"
            )
            blocks.append(
                f"{metric.name}, FY{report.period.fiscal_year}, {basis}: {shown}. Calculated by "
                f"FinSight as {metric.formula}."
            )
            meta.append(
                BlockMeta(label=f"{metric.name} FY{report.period.fiscal_year} (calculated)")
            )
    if not blocks:
        return None
    return Source(
        title=f"FinSight financial data: {company.name} ({company.ticker})",
        kind="financial_data",
        blocks=blocks,
        meta=meta,
        context="Figures stored by FinSight. Amounts are shown in ₹ crore; EPS per share.",
    )


def document_sources(
    db: Session,
    owner: User,
    question: str,
    *,
    company: Company | None,
    document_ids: list[uuid.UUID] | None,
    limit: int,
) -> list[Source]:
    stmt = select(Document).where(Document.owner_id == owner.id, Document.status == "ready")
    if document_ids:
        stmt = stmt.where(Document.id.in_(document_ids))
    elif company is not None:
        stmt = stmt.where(Document.company_id == company.id)
    documents = {d.id: d for d in db.scalars(stmt)}
    if document_ids and len(documents) != len(set(document_ids)):
        raise AppError("not_found", "Document not found", 404)
    if not documents:
        return []
    chunks = list(db.scalars(select(DocumentChunk).where(DocumentChunk.document_id.in_(documents))))
    hits = bm25(question, [Candidate(c.id, c.text) for c in chunks], limit)
    by_id = {c.id: c for c in chunks}
    grouped: dict[tuple[uuid.UUID, int], list[DocumentChunk]] = defaultdict(list)
    for hit in hits:
        chunk = by_id[int(str(hit.key))]
        grouped[(chunk.document_id, chunk.page_number)].append(chunk)
    sources: list[Source] = []
    for (doc_id, page), page_chunks in sorted(
        grouped.items(), key=lambda kv: (str(kv[0][0]), kv[0][1])
    ):
        doc = documents[doc_id]
        page_chunks.sort(key=lambda c: c.chunk_index)
        label = f"{doc.title}, p. {page}"
        sources.append(
            Source(
                title=label,
                kind="document_page",
                blocks=[c.text for c in page_chunks],
                meta=[
                    BlockMeta(label=label, document_id=str(doc_id), page_number=page, chunk_id=c.id)
                    for c in page_chunks
                ],
                context=f"Uploaded {doc.doc_type.replace('_', ' ')}"
                + (f" for FY{doc.fiscal_year}" if doc.fiscal_year else ""),
            )
        )
    return sources


@dataclass(frozen=True)
class ResearchResult:
    answer: LLMAnswer
    grounded: GroundedAnswer
    sources: list[Source]


def ask(
    db: Session,
    owner: User,
    llm: LLMProvider,
    question: str,
    *,
    company: Company | None,
    document_ids: list[uuid.UUID] | None,
    max_sources: int,
) -> ResearchResult:
    sources = document_sources(
        db, owner, question, company=company, document_ids=document_ids, limit=max_sources
    )
    if company is not None:
        data = financial_data_source(db, company)
        if data is not None:
            sources.append(data)
    if not sources:
        raise AppError(
            "no_sources",
            "No sources to answer from: upload an annual report or fetch statements first.",
            422,
        )
    try:
        answer = llm.answer(question, sources)
    except AIError as exc:
        raise ai_failure(exc) from None
    return ResearchResult(answer, ground_answer(answer, sources), sources)
