"""Request-ID, default security headers and access-log middleware (pure ASGI, so it also wraps
error responses)."""

import logging
import re
import time
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import request_id_var

logger = logging.getLogger("app.access")

_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
# Defaults for every API response (a route may set its own value, which is kept).
# no-store: responses carry user data and must not be cached by browsers or proxies.
_DEFAULT_HEADERS = (
    (b"x-content-type-options", b"nosniff"),
    (b"cache-control", b"no-store"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
)


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = dict(scope.get("headers") or []).get(b"x-request-id", b"").decode("latin-1")
        # Only trust a client-supplied ID if it is short and log-safe.
        request_id = incoming if _SAFE_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        token = request_id_var.set(request_id)
        # Also stash it on the request state: Starlette's 500 handler runs outside this
        # middleware, after the context var has been reset.
        scope.setdefault("state", {})["request_id"] = request_id
        start = time.perf_counter()
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = list(message.get("headers", []))
                present = {name.lower() for name, _ in headers}
                if b"x-request-id" not in present:
                    headers.append((b"x-request-id", request_id.encode()))
                headers += [(n, v) for n, v in _DEFAULT_HEADERS if n not in present]
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            logger.info(
                "request",
                extra={
                    "method": scope.get("method"),
                    "path": scope.get("path"),
                    "status": status_code,
                    "duration_ms": round((time.perf_counter() - start) * 1000, 2),
                },
            )
            request_id_var.reset(token)
