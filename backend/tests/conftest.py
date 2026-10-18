"""Test fixtures.

By default tests run against a throwaway SQLite file so they need no external services.
Set TEST_DATABASE_URL (e.g. the Postgres service in CI) to run the same suite against
PostgreSQL; tests marked ``postgres`` are skipped unless it is set.

Every API test gets a database migrated to head with Alembic (and downgraded afterwards), so
the migrations themselves are exercised on every run.
"""

import os
from collections.abc import Callable, Iterator
from datetime import date
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.security import reset_security_caches
from app.db.session import get_engine, get_sessionmaker
from app.providers.demo import DemoMarketDataProvider
from tests.fakes import FakeProvider

BACKEND_DIR = Path(__file__).resolve().parent.parent
TEST_PASSWORD = "correct-horse-battery-staple"
# A Monday: the demo provider's latest published trading day is then Friday 2026-10-16.
DEMO_TODAY = date(2026, 10, 19)


def _clear_caches() -> None:
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    reset_security_caches()


def alembic_config(url: str) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.attributes["configure_logger"] = False
    return cfg


@pytest.fixture
def database_url(tmp_path: Path) -> str:
    return os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{(tmp_path / 'test.db').as_posix()}"


@pytest.fixture
def test_env(database_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("FINSIGHT_ENVIRONMENT", "test")
    monkeypatch.setenv("FINSIGHT_DATABASE_URL", database_url)
    monkeypatch.setenv("FINSIGHT_LOG_JSON", "false")
    monkeypatch.setenv("FINSIGHT_JWT_SECRET", "test-secret-" + "x" * 40)
    monkeypatch.delenv("FINSIGHT_SEC_USER_AGENT", raising=False)
    for name in (
        "FINSIGHT_DEFAULT_MARKET",
        "FINSIGHT_MARKET_DATA_PROVIDER",
        "FINSIGHT_FUNDAMENTALS_PROVIDER",
    ):
        monkeypatch.delenv(name, raising=False)
    _clear_caches()
    yield
    _clear_caches()


@pytest.fixture
def us_market(test_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run a test against the optional US (SEC EDGAR) market instead of the IN default."""
    monkeypatch.setenv("FINSIGHT_DEFAULT_MARKET", "US")
    get_settings.cache_clear()


@pytest.fixture
def migrated(test_env: None, database_url: str) -> Iterator[None]:
    cfg = alembic_config(database_url)
    command.upgrade(cfg, "head")
    yield
    get_engine().dispose()
    command.downgrade(cfg, "base")


@pytest.fixture
def fake_provider() -> FakeProvider:
    return FakeProvider()


@pytest.fixture
def client(migrated: None, fake_provider: FakeProvider) -> Iterator[TestClient]:
    from app.main import create_app
    from app.services import instruments

    instruments._last_sync.clear()  # directory-sync cooldown is process-global
    app = create_app()
    app.state.provider = fake_provider
    # Indian market: deterministic demo data and a fixed "today" (IST).
    app.state.demo_provider = DemoMarketDataProvider(lambda: DEMO_TODAY)
    app.state.today = lambda: DEMO_TODAY
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    get_engine().dispose()


@pytest.fixture
def register_and_login(client: TestClient) -> Callable[[str], dict[str, str]]:
    """Create a user and return Authorization headers for them."""

    def _make(email: str) -> dict[str, str]:
        r = client.post("/api/v1/auth/register", json={"email": email, "password": TEST_PASSWORD})
        assert r.status_code == 201, r.text
        r = client.post("/api/v1/auth/login", json={"email": email, "password": TEST_PASSWORD})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    return _make


@pytest.fixture
def auth(register_and_login: Callable[[str], dict[str, str]]) -> dict[str, str]:
    return register_and_login("alice@example.com")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.environ.get("TEST_DATABASE_URL", "").startswith("postgresql"):
        return
    skip = pytest.mark.skip(reason="TEST_DATABASE_URL (PostgreSQL) not set")
    for item in items:
        if "postgres" in item.keywords:
            item.add_marker(skip)
