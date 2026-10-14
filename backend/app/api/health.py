"""Liveness and readiness probes."""

import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import __version__
from app.core.config import get_settings
from app.db.session import check_database, get_db

logger = logging.getLogger("app.health")

router = APIRouter(prefix="/health", tags=["health"])


class LivenessResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str
    environment: str


class ReadinessResponse(BaseModel):
    status: Literal["ok", "unavailable"]
    checks: dict[str, Literal["ok", "error"]]


@router.get("/live", response_model=LivenessResponse)
def liveness() -> LivenessResponse:
    """The process is up. Does not touch dependencies."""
    settings = get_settings()
    return LivenessResponse(
        status="ok",
        service=settings.app_name,
        version=__version__,
        environment=settings.environment,
    )


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse}},
)
def readiness(db: Annotated[Session, Depends(get_db)]) -> ReadinessResponse | JSONResponse:
    """The service can serve traffic: database reachable."""
    try:
        check_database(db)
    except Exception:
        logger.warning("readiness_db_check_failed", exc_info=True)
        body = ReadinessResponse(status="unavailable", checks={"database": "error"})
        return JSONResponse(status_code=503, content=body.model_dump())
    return ReadinessResponse(status="ok", checks={"database": "ok"})
