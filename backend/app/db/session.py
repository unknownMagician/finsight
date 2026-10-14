"""Engine and session management.

The engine is created lazily from settings so tests can point at a different database.
"""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    url = settings.database_url.get_secret_value()
    kwargs: dict[str, object] = {"echo": settings.db_echo, "pool_pre_ping": True}
    if not url.startswith("sqlite"):
        kwargs["pool_size"] = settings.db_pool_size
    return create_engine(url, **kwargs)


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session."""
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()


def check_database(session: Session) -> None:
    """Raise if the database is unreachable."""
    session.execute(text("SELECT 1"))
