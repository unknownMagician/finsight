"""AI research assistant: questions answered only from cited, verified sources."""

import uuid

from fastapi import APIRouter, Request

from app.api.deps import LLM, AIRateLimit, CurrentUser, DbSession, resolve_market
from app.core.config import get_settings
from app.schemas import (
    AnswerSegmentOut,
    CitationOut,
    GroundingIssueOut,
    ResearchAnswerOut,
    ResearchAskRequest,
    ResearchSourceOut,
    ResearchStatusOut,
)
from app.services import companies as company_service
from app.services import research as service

router = APIRouter(prefix="/research", tags=["research"])


@router.get("/status", response_model=ResearchStatusOut)
def research_status(_: CurrentUser, request: Request) -> ResearchStatusOut:
    llm = getattr(request.app.state, "llm", None)
    settings = get_settings()
    configured = llm is not None or settings.anthropic_api_key is not None
    return ResearchStatusOut(
        configured=configured,
        provider=(llm.name if llm else "anthropic") if configured else None,
        model=(llm.model if llm else settings.ai_model) if configured else None,
    )


def _uuid(value: str | None) -> uuid.UUID | None:
    return uuid.UUID(value) if value else None


@router.post("/ask", response_model=ResearchAnswerOut, dependencies=[AIRateLimit])
def ask(user: CurrentUser, db: DbSession, llm: LLM, body: ResearchAskRequest) -> ResearchAnswerOut:
    company = (
        company_service.get_company(db, body.ticker, resolve_market(body.market))
        if body.ticker
        else None
    )
    result = service.ask(
        db,
        user,
        llm,
        body.question,
        company=company,
        document_ids=body.document_ids,
        max_sources=get_settings().ai_max_sources,
    )
    sources = result.sources
    segments = []
    for segment in result.grounded.segments:
        citations = []
        for c in segment.citations:
            source = sources[c.source_index]
            meta = source.meta[c.start_block]
            citations.append(
                CitationOut(
                    source=c.source_index + 1,
                    cited_text=c.cited_text,
                    label=meta.label,
                    document_id=_uuid(meta.document_id),
                    page_number=meta.page_number,
                )
            )
        segments.append(AnswerSegmentOut(text=segment.text, citations=citations))
    return ResearchAnswerOut(
        question=body.question,
        model=result.answer.model,
        grounding=result.grounded.status,
        segments=segments,
        sources=[
            ResearchSourceOut(
                number=i + 1,
                title=s.title,
                kind=s.kind,
                document_id=_uuid(s.meta[0].document_id) if s.meta else None,
                page_number=s.meta[0].page_number if s.meta else None,
            )
            for i, s in enumerate(sources)
        ],
        issues=[
            GroundingIssueOut(
                code=i.code,
                segment=i.segment_index if i.segment_index >= 0 else None,
                message=i.message,
            )
            for i in result.grounded.issues
        ],
        input_tokens=result.answer.input_tokens,
        output_tokens=result.answer.output_tokens,
    )
