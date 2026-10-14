"""Uniform error envelope and exception handlers.

Every error response has the shape::

    {"error": {"code": "...", "message": "...", "request_id": "...", "details": ...}}

Unhandled exceptions are logged with a stack trace server-side but only a generic message is
returned to the client, so internals never leak.
"""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import request_id_var

logger = logging.getLogger("app.errors")


class AppError(Exception):
    """Domain error with a stable machine-readable code."""

    def __init__(self, code: str, message: str, status_code: int = 400, details: Any = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


def _request_id(request: Request) -> str | None:
    return request_id_var.get() or getattr(request.state, "request_id", None)


def _envelope(
    request: Request, code: str, message: str, status_code: int, details: Any = None
) -> JSONResponse:
    request_id = _request_id(request)
    body: dict[str, Any] = {"code": code, "message": message, "request_id": request_id}
    if details is not None:
        body["details"] = details
    headers = {"X-Request-ID": request_id} if request_id else None
    return JSONResponse(status_code=status_code, content={"error": body}, headers=headers)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        return _envelope(request, exc.code, exc.message, exc.status_code, exc.details)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _envelope(request, "http_error", str(exc.detail), exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"loc": list(err.get("loc", ())), "msg": err.get("msg"), "type": err.get("type")}
            for err in exc.errors()
        ]
        return _envelope(request, "validation_error", "Request validation failed", 422, details)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "unhandled_exception", exc_info=exc, extra={"request_id": _request_id(request)}
        )
        return _envelope(request, "internal_error", "An unexpected error occurred", 500)
