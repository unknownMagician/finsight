"""Migration chain checks: upgrade/downgrade round-trip and no drift from the ORM models."""

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect

from app.models import Base
from tests.conftest import alembic_config

EXPECTED_TABLES = {
    "alembic_version",
    "users",
    "companies",
    "financial_periods",
    "financial_line_items",
    "watchlists",
    "watchlist_items",
    "saved_valuations",
}


def test_single_head() -> None:
    script = ScriptDirectory.from_config(alembic_config("sqlite://"))
    assert len(script.get_heads()) == 1


def test_upgrade_downgrade_roundtrip(database_url: str) -> None:
    cfg = alembic_config(database_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    engine = create_engine(database_url)
    try:
        assert set(inspect(engine).get_table_names()) == EXPECTED_TABLES
    finally:
        engine.dispose()
    command.downgrade(cfg, "base")


def test_models_match_migrations(database_url: str) -> None:
    cfg = alembic_config(database_url)
    command.upgrade(cfg, "head")
    engine = create_engine(database_url)
    try:
        with engine.connect() as conn:
            diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    finally:
        engine.dispose()
    command.downgrade(cfg, "base")
    assert diff == [], f"ORM models and migrations have drifted: {diff}"


@pytest.mark.postgres
def test_postgres_dialect(database_url: str) -> None:
    engine = create_engine(database_url)
    try:
        assert engine.dialect.name == "postgresql"
    finally:
        engine.dispose()
