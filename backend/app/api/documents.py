"""Annual-report uploads and AI fact extraction (owner-scoped)."""

from typing import Annotated

from fastapi import APIRouter, File, Form, Path, Response, UploadFile, status

from app.api.deps import (
    LLM,
    AIRateLimit,
    CurrentUser,
    DbSession,
    UploadRateLimit,
    parse_uuid,
    resolve_market,
)
from app.core.config import get_settings
from app.core.errors import AppError
from app.models import Document
from app.schemas import (
    CompanyRefOut,
    DocumentFactOut,
    DocumentOut,
    DocumentPageOut,
    ExtractFactsRequest,
    Market,
)
from app.services import companies as company_service
from app.services import documents as service

router = APIRouter(prefix="/documents", tags=["documents"])

DOC_TYPES = {"annual_report", "quarterly_results", "other"}


def _out(document: Document) -> DocumentOut:
    company = document.company
    return DocumentOut(
        id=document.id,
        title=document.title,
        doc_type=document.doc_type,
        fiscal_year=document.fiscal_year,
        filename=document.filename,
        size_bytes=document.size_bytes,
        page_count=document.page_count,
        pages_with_text=document.pages_with_text,
        status=document.status,
        company=CompanyRefOut(market=company.market, ticker=company.ticker, name=company.name)
        if company
        else None,
        facts=[DocumentFactOut.model_validate(f) for f in document.facts],
        created_at=document.created_at,
    )


async def _read_limited(file: UploadFile, limit: int) -> bytes:
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise AppError("file_too_large", f"Upload exceeds {limit // (1024 * 1024)} MB", 413)
    return data


@router.post(
    "",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[UploadRateLimit],
)
async def upload_document(
    user: CurrentUser,
    db: DbSession,
    file: Annotated[UploadFile, File()],
    title: Annotated[str, Form(min_length=1, max_length=200)],
    ticker: Annotated[str | None, Form(max_length=30)] = None,
    market: Annotated[Market | None, Form()] = None,
    fiscal_year: Annotated[int | None, Form(ge=1990, le=2200)] = None,
    doc_type: Annotated[str, Form()] = "annual_report",
) -> DocumentOut:
    if doc_type not in DOC_TYPES:
        raise AppError("invalid_request", f"doc_type must be one of {sorted(DOC_TYPES)}", 422)
    settings = get_settings()
    limit = settings.upload_max_mb * 1024 * 1024
    data = await _read_limited(file, limit)
    company = company_service.get_company(db, ticker, resolve_market(market)) if ticker else None
    document = service.upload(
        db,
        user,
        data,
        filename=file.filename or "upload.pdf",
        title=title.strip(),
        company=company,
        fiscal_year=fiscal_year,
        doc_type=doc_type,
        max_bytes=limit,
        max_pages=settings.upload_max_pages,
    )
    return _out(document)


@router.get("", response_model=list[DocumentOut])
def list_documents(
    user: CurrentUser, db: DbSession, ticker: str | None = None, market: Market | None = None
) -> list[DocumentOut]:
    company = company_service.get_company(db, ticker, resolve_market(market)) if ticker else None
    return [_out(d) for d in service.list_for(db, user, company)]


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(user: CurrentUser, db: DbSession, document_id: str) -> DocumentOut:
    return _out(service.get_owned(db, user, parse_uuid(document_id, "Document")))


@router.get("/{document_id}/pages/{page_number}", response_model=DocumentPageOut)
def get_page(
    user: CurrentUser,
    db: DbSession,
    document_id: str,
    page_number: Annotated[int, Path(ge=1, le=100000)],
) -> DocumentPageOut:
    page = service.get_page(db, user, parse_uuid(document_id, "Document"), page_number)
    return DocumentPageOut(page_number=page.page_number, text=page.text)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(user: CurrentUser, db: DbSession, document_id: str) -> Response:
    service.delete(db, user, parse_uuid(document_id, "Document"))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{document_id}/facts/extract", response_model=DocumentOut, dependencies=[AIRateLimit])
def extract_facts(
    user: CurrentUser,
    db: DbSession,
    llm: LLM,
    document_id: str,
    body: ExtractFactsRequest | None = None,
) -> DocumentOut:
    """Ask the AI to read key figures off the report; each is verified against the page."""
    doc_id = parse_uuid(document_id, "Document")
    service.get_owned(db, user, doc_id)  # 404 before spending an AI call
    metrics = body.metrics if body else None
    return _out(service.extract_facts(db, user, doc_id, llm, metrics))
