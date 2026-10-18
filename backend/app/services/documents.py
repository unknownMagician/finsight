"""Uploaded annual reports. Every query is owner-scoped; another user's document is a 404."""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.ai.base import AIError, AIRateLimitedError, AIRefusalError, LLMProvider
from app.ai.grounding import verify_fact
from app.ai.retrieval import Candidate, bm25
from app.core.errors import AppError
from app.documents.chunking import chunk_page
from app.documents.pdf import PdfError, extract_pdf
from app.models import Company, Document, DocumentChunk, DocumentFact, DocumentPage, User

logger = logging.getLogger("app.documents")

MAX_DOCUMENTS_PER_USER = 50
EXTRACT_PAGE_LIMIT = 12
DEFAULT_METRICS = [
    "Revenue from operations",
    "Total income",
    "EBITDA",
    "Profit before tax",
    "Net profit / profit after tax",
    "Basic EPS",
    "Diluted EPS",
    "Total assets",
    "Total equity",
    "Total borrowings",
    "Cash and cash equivalents",
    "Dividend per share",
]


def _not_found() -> AppError:
    return AppError("not_found", "Document not found", 404)


def upload(
    db: Session,
    owner: User,
    data: bytes,
    *,
    filename: str,
    title: str,
    company: Company | None,
    fiscal_year: int | None,
    doc_type: str,
    max_bytes: int,
    max_pages: int,
) -> Document:
    if len(data) > max_bytes:
        raise AppError("file_too_large", f"Upload exceeds {max_bytes // (1024 * 1024)} MB", 413)
    count = len(list(db.scalars(select(Document.id).where(Document.owner_id == owner.id))))
    if count >= MAX_DOCUMENTS_PER_USER:
        raise AppError("limit_exceeded", f"At most {MAX_DOCUMENTS_PER_USER} documents", 409)
    try:
        pdf = extract_pdf(data, max_pages=max_pages)
    except PdfError as exc:
        raise AppError("invalid_pdf", str(exc), 422) from None
    duplicate = db.scalar(
        select(Document.id).where(Document.owner_id == owner.id, Document.sha256 == pdf.sha256)
    )
    if duplicate is not None:
        raise AppError(
            "document_exists", "You already uploaded this file", 409, details={"id": str(duplicate)}
        )

    pages_with_text = sum(1 for p in pdf.pages if p)
    document = Document(
        owner_id=owner.id,
        company_id=company.id if company else None,
        title=title,
        doc_type=doc_type,
        fiscal_year=fiscal_year,
        filename=filename[:255],
        sha256=pdf.sha256,
        size_bytes=len(data),
        page_count=pdf.page_count,
        pages_with_text=pages_with_text,
        status="ready" if pages_with_text else "no_text",
    )
    for number, text in enumerate(pdf.pages, start=1):
        document.pages.append(DocumentPage(page_number=number, text=text))
        for index, chunk in enumerate(chunk_page(text)):
            document.chunks.append(DocumentChunk(page_number=number, chunk_index=index, text=chunk))
    db.add(document)
    db.commit()
    logger.info(
        "document_uploaded",
        extra={"pages": pdf.page_count, "pages_with_text": pages_with_text, "bytes": len(data)},
    )
    return get_owned(db, owner, document.id)


def list_for(db: Session, owner: User, company: Company | None = None) -> list[Document]:
    stmt = (
        select(Document)
        .where(Document.owner_id == owner.id)
        .options(selectinload(Document.company), selectinload(Document.facts))
        .order_by(Document.created_at.desc())
    )
    if company is not None:
        stmt = stmt.where(Document.company_id == company.id)
    return list(db.scalars(stmt))


def get_owned(db: Session, owner: User, document_id: uuid.UUID) -> Document:
    document = db.scalar(
        select(Document)
        .where(Document.id == document_id, Document.owner_id == owner.id)
        .options(selectinload(Document.company), selectinload(Document.facts))
    )
    if document is None:
        raise _not_found()
    return document


def get_page(db: Session, owner: User, document_id: uuid.UUID, page_number: int) -> DocumentPage:
    get_owned(db, owner, document_id)
    page = db.scalar(
        select(DocumentPage).where(
            DocumentPage.document_id == document_id, DocumentPage.page_number == page_number
        )
    )
    if page is None:
        raise AppError("not_found", f"Page {page_number} not found", 404)
    return page


def delete(db: Session, owner: User, document_id: uuid.UUID) -> None:
    db.delete(get_owned(db, owner, document_id))
    db.commit()


def ai_failure(exc: AIError) -> AppError:
    if isinstance(exc, AIRefusalError):
        return AppError("ai_refused", "The AI model declined this request", 422)
    if isinstance(exc, AIRateLimitedError):
        return AppError("ai_rate_limited", "The AI provider is rate limiting; try again later", 503)
    logger.warning("ai_error", extra={"error": str(exc)})
    return AppError("ai_unavailable", "The AI provider is unavailable", 502)


def extract_facts(
    db: Session,
    owner: User,
    document_id: uuid.UUID,
    llm: LLMProvider,
    metrics: list[str] | None = None,
) -> Document:
    """Ask the model for figures on the most relevant pages, then verify each one."""
    document = get_owned(db, owner, document_id)
    if document.status != "ready":
        raise AppError("no_text", "This PDF has no extractable text (scanned; no OCR)", 422)
    wanted = metrics or DEFAULT_METRICS
    pages = list(
        db.scalars(
            select(DocumentPage).where(
                DocumentPage.document_id == document.id, DocumentPage.text != ""
            )
        )
    )
    hits = bm25(
        " ".join(wanted), [Candidate(p.page_number, p.text) for p in pages], EXTRACT_PAGE_LIMIT
    )
    chosen = sorted(int(str(h.key)) for h in hits) or [
        p.page_number for p in pages[:EXTRACT_PAGE_LIMIT]
    ]
    text_by_page = {p.page_number: p.text for p in pages}
    try:
        raw = llm.extract_facts([(n, text_by_page[n]) for n in chosen], wanted)
    except AIError as exc:
        raise ai_failure(exc) from None

    now = datetime.now(UTC)
    document.facts.clear()
    db.flush()
    for fact in raw:
        # Only pages that were actually sent count; anything else cannot have been read.
        check = verify_fact(
            fact, text_by_page.get(fact.page_number) if fact.page_number in chosen else None
        )
        if check.value is None:
            continue
        document.facts.append(
            DocumentFact(
                metric=fact.metric,
                value=check.value,
                unit=fact.unit,
                currency=fact.currency,
                period_label=fact.period_label,
                period_end=fact.period_end,
                basis=fact.basis,
                page_number=fact.page_number,
                quote=fact.quote,
                status=check.status,
                verification_note=check.note,
                model=llm.model,
                extracted_at=now,
            )
        )
    db.commit()
    logger.info("facts_extracted", extra={"pages_sent": len(chosen), "facts": len(raw)})
    db.expire_all()
    return get_owned(db, owner, document_id)
