"""research reports

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-18
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0005'
down_revision: str | None = '0004'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:

    op.create_table('research_reports',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('owner_id', sa.Uuid(), nullable=False),
    sa.Column('company_id', sa.Integer(), nullable=True),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('ticker', sa.String(length=30), nullable=False),
    sa.Column('includes_ai', sa.Boolean(), nullable=False),
    sa.Column('content', sa.JSON(), nullable=False),
    sa.Column('engine_version', sa.String(length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], name=op.f('fk_research_reports_company_id_companies'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], name=op.f('fk_research_reports_owner_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_research_reports'))
    )
    with op.batch_alter_table('research_reports', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_research_reports_company_id'), ['company_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_research_reports_owner_id'), ['owner_id'], unique=False)




def downgrade() -> None:

    with op.batch_alter_table('research_reports', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_research_reports_owner_id'))
        batch_op.drop_index(batch_op.f('ix_research_reports_company_id'))

    op.drop_table('research_reports')

