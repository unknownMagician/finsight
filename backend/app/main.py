"""FastAPI application factory."""

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import auth, calculations, companies, health, market, valuations, watchlists
from app.core.cache import TTLCache
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.core.ratelimit import RateLimiter
from app.core.security import validate_security_settings
from app.services.market_data import today_ist

API_PREFIX = "/api/v1"


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    validate_security_settings()

    is_prod = settings.environment == "production"
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        docs_url=None if is_prod else "/docs",
        redoc_url=None,
        openapi_url=None if is_prod else "/openapi.json",
    )
    app.state.rate_limiter = RateLimiter()
    app.state.market_cache = TTLCache(settings.market_data_cache_ttl_seconds)
    app.state.today = today_ist

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID", "Retry-After"],
    )
    # Outermost, so request IDs are attached to every response including errors.
    app.add_middleware(RequestContextMiddleware)

    register_exception_handlers(app)

    api = APIRouter(prefix=API_PREFIX)
    for module in (health, auth, companies, market, calculations, watchlists, valuations):
        api.include_router(module.router)
    app.include_router(api)
    return app


app = create_app()
