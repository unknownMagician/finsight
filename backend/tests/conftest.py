"""Test fixtures.

By default tests run against a throwaway SQLite file so they need no external services.
Set TEST_DATABASE_URL (e.g. the Postgres service in CI) to run the same suite against
PostgreSQL; tests marked ``postgres`` are skipped unless it is set.
"""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.session import get_engine, get_sessionmaker

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _clear_caches() -> None:
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()


@pytest.fixture
def database_url(tmp_path: Path) -> str:
    return os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{(tmp_path / 'test.db').as_posix()}"


@pytest.fixture
def client(database_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("FINSIGHT_ENVIRONMENT", "test")
    monkeypatch.setenv("FINSIGHT_DATABASE_URL", database_url)
    monkeypatch.setenv("FINSIGHT_LOG_JSON", "false")
    _clear_caches()
    from app.main import create_app

    with TestClient(create_app(), raise_server_exceptions=False) as test_client:
        yield test_client
    get_engine().dispose()
    _clear_caches()


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.environ.get("TEST_DATABASE_URL", "").startswith("postgresql"):
        return
    skip = pytest.mark.skip(reason="TEST_DATABASE_URL (PostgreSQL) not set")
    for item in items:
        if "postgres" in item.keywords:
            item.add_marker(skip)
