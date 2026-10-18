"""Migration chain checks: upgrade/downgrade round-trip and no drift from the ORM models."""

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

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
    "instruments",
    "documents",
    "document_pages",
    "document_chunks",
    "document_facts",
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


def test_0003_preserves_sec_data_and_downgrade_removes_only_indian_rows(
    database_url: str,
) -> None:
    cfg = alembic_config(database_url)
    command.upgrade(cfg, "0002")
    engine = create_engine(database_url)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO companies (id, ticker, cik, name, created_at, updated_at) "
                    "VALUES (1, 'SYNW', '0000000042', 'Synthetic Widgets', "
                    "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO financial_periods (id, company_id, fiscal_year, fiscal_period, "
                    "period_end, currency, scale, kind, source_provider, retrieved_at, "
                    "created_at, updated_at) VALUES (1, 1, 2024, 'FY', '2024-09-28', 'USD', "
                    "'units', 'reported', 'sec_edgar', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, "
                    "CURRENT_TIMESTAMP)"
                )
            )
        command.upgrade(cfg, "head")
        with engine.begin() as conn:
            assert conn.execute(text("SELECT market FROM companies")).scalar_one() == "US"
            assert conn.execute(text("SELECT basis FROM financial_periods")).scalar_one() == (
                "unspecified"
            )
            conn.execute(
                text(
                    "INSERT INTO companies (id, market, ticker, name, created_at, updated_at) "
                    "VALUES (2, 'IN', 'SYNW', 'Indian namesake', "
                    "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                )
            )
        command.downgrade(cfg, "0002")
        with engine.connect() as conn:
            assert conn.execute(text("SELECT ticker FROM companies")).scalars().all() == ["SYNW"]
            assert conn.execute(text("SELECT COUNT(*) FROM financial_periods")).scalar_one() == 1
    finally:
        engine.dispose()
    command.downgrade(cfg, "base")
