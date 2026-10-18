"""Research reports (owner-scoped snapshots) and their export formats."""

import re
from typing import Literal

from fastapi import APIRouter, Request, Response, status

from app.api.deps import (
    ComputeRateLimit,
    CurrentUser,
    DbSession,
    MarketCache,
    MarketProvider,
    Today,
    enforce_user_limit,
    get_llm,
    parse_uuid,
    resolve_market,
)
from app.core.config import get_settings
from app.models import ResearchReport
from app.reports.render import to_csv, to_html, to_markdown
from app.schemas import ReportCreate, ReportOut, ReportSummaryOut
from app.services import companies as company_service
from app.services import reports as service

router = APIRouter(prefix="/reports", tags=["reports"])

ExportFormat = Literal["json", "md", "html", "csv"]
MEDIA = {
    "json": "application/json",
    "md": "text/markdown; charset=utf-8",
    "html": "text/html; charset=utf-8",
    "csv": "text/csv; charset=utf-8",
}


def _out(report: ResearchReport) -> ReportOut:
    return ReportOut(
        id=report.id,
        title=report.title,
        ticker=report.ticker,
        includes_ai=report.includes_ai,
        engine_version=report.engine_version,
        created_at=report.created_at,
        content=report.content,
    )


@router.post(
    "",
    response_model=ReportOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[ComputeRateLimit],
)
def create_report(
    user: CurrentUser,
    db: DbSession,
    request: Request,
    provider: MarketProvider,
    cache: MarketCache,
    today: Today,
    body: ReportCreate,
) -> ReportOut:
    company = company_service.get_company(db, body.ticker, resolve_market(body.market))
    llm = None
    if body.include_ai:
        llm = get_llm(request)  # 503 ai_not_configured when no key
        # AI summaries count against the same per-user AI budget as /research/ask.
        enforce_user_limit(request, user, "ai", "rate_limit_ai_per_hour", 3600)
    settings = get_settings()
    report = service.generate(
        db,
        user,
        company,
        provider=provider,
        cache=cache,
        exchange=body.exchange,
        basis=body.basis,
        llm=llm,
        title=body.title,
        stale_after_days=settings.market_data_stale_after_days,
        max_sources=settings.ai_max_sources,
        today=today,
    )
    return _out(report)


@router.get("", response_model=list[ReportSummaryOut])
def list_reports(user: CurrentUser, db: DbSession) -> list[ReportSummaryOut]:
    return [ReportSummaryOut.model_validate(r) for r in service.list_for(db, user)]


@router.get("/{report_id}", response_model=ReportOut)
def get_report(user: CurrentUser, db: DbSession, report_id: str) -> ReportOut:
    return _out(service.get_owned(db, user, parse_uuid(report_id, "Report")))


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_report(user: CurrentUser, db: DbSession, report_id: str) -> Response:
    service.delete(db, user, parse_uuid(report_id, "Report"))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{report_id}/export")
def export_report(
    user: CurrentUser, db: DbSession, report_id: str, format: ExportFormat = "md"
) -> Response:
    report = service.get_owned(db, user, parse_uuid(report_id, "Report"))
    content = service.content_of(report)
    body = {
        "json": lambda: content.model_dump_json(indent=2),
        "md": lambda: to_markdown(content),
        "html": lambda: to_html(content),
        "csv": lambda: to_csv(content),
    }[format]()
    slug = re.sub(r"[^A-Za-z0-9]+", "-", f"{report.ticker}-{report.created_at:%Y%m%d}").strip("-")
    return Response(
        content=body,
        media_type=MEDIA[format],
        headers={
            "Content-Disposition": f'attachment; filename="finsight-{slug}.{format}"',
            "X-Content-Type-Options": "nosniff",
        },
    )
