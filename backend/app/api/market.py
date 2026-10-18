"""Market-data provider status, capabilities, freshness and directory refresh."""

from fastapi import APIRouter, Request

from app.api.deps import CurrentUser, DbSession, IngestRateLimit, MarketCache, MarketProvider
from app.core.config import get_settings
from app.core.errors import AppError
from app.providers.base import Capability, ProviderError
from app.providers.registry import USAGE_TERMS, ProviderConfigError, build_fundamentals_provider
from app.schemas import DirectorySyncOut, MarketStatusOut, ProviderInfoOut
from app.services import instruments as instrument_service
from app.services import market_data

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/status", response_model=MarketStatusOut)
def market_status(
    _: CurrentUser, request: Request, provider: MarketProvider, cache: MarketCache
) -> MarketStatusOut:
    settings = get_settings()
    status, _cached = market_data.provider_status(provider, cache)

    fundamentals = getattr(request.app.state, "fundamentals_provider", None)
    fundamentals_error: str | None = None
    if fundamentals is None:
        try:
            fundamentals = build_fundamentals_provider(
                settings, getattr(request.app.state, "demo_provider", None)
            )
        except ProviderConfigError as exc:
            fundamentals_error = str(exc)
    # Capabilities are scoped by role: the demo provider implements both roles, but statements
    # only count when the fundamentals role is configured, and vice versa.
    market_caps = set(provider.capabilities) - {Capability.FINANCIAL_STATEMENTS}
    fundamentals_caps = (
        set(fundamentals.capabilities) & {Capability.FINANCIAL_STATEMENTS}
        if fundamentals
        else set()
    )
    nature = "demo" if provider.name == "demo" else "end_of_day"
    providers = [
        ProviderInfoOut(
            role="market_data",
            name=provider.name,
            configured=True,
            capabilities=sorted(c.value for c in market_caps),
            data_nature=nature,
            usage_terms=USAGE_TERMS.get(provider.name, ""),
        ),
        ProviderInfoOut(
            role="fundamentals_in",
            name=fundamentals.name if fundamentals else settings.fundamentals_provider,
            configured=fundamentals is not None,
            capabilities=sorted(c.value for c in fundamentals_caps),
            data_nature="demo" if fundamentals and fundamentals.name == "demo" else None,
            usage_terms=fundamentals_error
            or USAGE_TERMS.get(fundamentals.name if fundamentals else "", "Disabled."),
        ),
        ProviderInfoOut(
            role="fundamentals_us",
            name="sec_edgar",
            configured=bool(settings.sec_user_agent),
            capabilities=[Capability.FINANCIAL_STATEMENTS.value] if settings.sec_user_agent else [],
            data_nature=None,
            usage_terms=USAGE_TERMS["sec_edgar"],
        ),
    ]
    return MarketStatusOut(
        default_market=settings.default_market,
        providers=providers,
        reachable=status.reachable,
        latest_trading_date=status.latest_trading_date,
        published_at=status.published_at,
        unavailable_capabilities=sorted(
            c.value for c in set(Capability) - market_caps - fundamentals_caps
        ),
    )


@router.post("/directory/sync", response_model=DirectorySyncOut, dependencies=[IngestRateLimit])
def sync_directory(_: CurrentUser, db: DbSession, provider: MarketProvider) -> DirectorySyncOut:
    """Refresh the Indian instrument directory from the market-data provider's latest snapshot."""
    try:
        report = instrument_service.sync_directory(db, provider)
    except ProviderError:
        raise AppError(
            "provider_unavailable", "The market-data provider is unavailable", 502
        ) from None
    return DirectorySyncOut(**report.__dict__)
