"""Migration chain checks: upgrade/downgrade round-trip and no drift from the ORM models."""

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect

from app.models import Base
from tests.conftest import BACKEND_DIR


def _config(url: str) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.attributes["configure_logger"] = False
    return cfg


def test_single_head() -> None:
    script = ScriptDirectory.from_config(_config("sqlite://"))
    assert len(script.get_heads()) == 1


def test_upgrade_downgrade_roundtrip(database_url: str) -> None:
    cfg = _config(database_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    engine = create_engine(database_url)
    try:
        assert "alembic_version" in inspect(engine).get_table_names()
    finally:
        engine.dispose()


def test_models_match_migrations(database_url: str) -> None:
    command.upgrade(_config(database_url), "head")
    engine = create_engine(database_url)
    try:
        with engine.connect() as conn:
            diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    finally:
        engine.dispose()
    assert diff == [], f"ORM models and migrations have drifted: {diff}"


@pytest.mark.postgres
def test_postgres_dialect(database_url: str) -> None:
    engine = create_engine(database_url)
    try:
        assert engine.dialect.name == "postgresql"
    finally:
        engine.dispose()
