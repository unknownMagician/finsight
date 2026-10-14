"""baseline: empty schema, establishes the migration chain

Revision ID: 0001
Revises:
Create Date: 2026-10-15

Phase 1 intentionally creates no domain tables. Domain tables (users, companies,
financial statements, ...) are added by later revisions as their features are built.
"""
from collections.abc import Sequence

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
