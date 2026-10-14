"""core tables: users, companies, financial periods + line items, watchlists, saved valuations

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-15
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0002'
down_revision: str | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('companies',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('ticker', sa.String(length=20), nullable=False),
    sa.Column('cik', sa.String(length=10), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('exchange', sa.String(length=50), nullable=True),
    sa.Column('last_ingested_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_companies')),
    sa.UniqueConstraint('cik', name=op.f('uq_companies_cik')),
    sa.UniqueConstraint('ticker', name=op.f('uq_companies_ticker'))
    )
    op.create_table('users',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('display_name', sa.String(length=100), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
    sa.UniqueConstraint('email', name=op.f('uq_users_email'))
    )
    op.create_table('financial_periods',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('company_id', sa.Integer(), nullable=False),
    sa.Column('fiscal_year', sa.Integer(), nullable=False),
    sa.Column('fiscal_period', sa.String(length=2), nullable=False),
    sa.Column('period_start', sa.Date(), nullable=True),
    sa.Column('period_end', sa.Date(), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('scale', sa.String(length=10), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('source_provider', sa.String(length=100), nullable=False),
    sa.Column('source_url', sa.String(length=2000), nullable=True),
    sa.Column('retrieved_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], name=op.f('fk_financial_periods_company_id_companies'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_financial_periods')),
    sa.UniqueConstraint('company_id', 'fiscal_year', 'fiscal_period', name=op.f('uq_financial_periods_company_id'))
    )
    with op.batch_alter_table('financial_periods', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_financial_periods_company_id'), ['company_id'], unique=False)

    op.create_table('saved_valuations',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('owner_id', sa.Uuid(), nullable=False),
    sa.Column('company_id', sa.Integer(), nullable=True),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('method', sa.String(length=30), nullable=False),
    sa.Column('inputs', sa.JSON(), nullable=False),
    sa.Column('result', sa.JSON(), nullable=False),
    sa.Column('engine_version', sa.String(length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], name=op.f('fk_saved_valuations_company_id_companies'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], name=op.f('fk_saved_valuations_owner_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_saved_valuations'))
    )
    with op.batch_alter_table('saved_valuations', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_saved_valuations_owner_id'), ['owner_id'], unique=False)

    op.create_table('watchlists',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('owner_id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], name=op.f('fk_watchlists_owner_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_watchlists')),
    sa.UniqueConstraint('owner_id', 'name', name=op.f('uq_watchlists_owner_id'))
    )
    with op.batch_alter_table('watchlists', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_watchlists_owner_id'), ['owner_id'], unique=False)

    op.create_table('financial_line_items',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('period_id', sa.Integer(), nullable=False),
    sa.Column('statement', sa.String(length=20), nullable=False),
    sa.Column('item', sa.String(length=64), nullable=False),
    sa.Column('value', sa.Numeric(precision=28, scale=6), nullable=False),
    sa.Column('source_concept', sa.String(length=255), nullable=True),
    sa.Column('source_accession', sa.String(length=30), nullable=True),
    sa.ForeignKeyConstraint(['period_id'], ['financial_periods.id'], name=op.f('fk_financial_line_items_period_id_financial_periods'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_financial_line_items')),
    sa.UniqueConstraint('period_id', 'statement', 'item', name=op.f('uq_financial_line_items_period_id'))
    )
    with op.batch_alter_table('financial_line_items', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_financial_line_items_period_id'), ['period_id'], unique=False)

    op.create_table('watchlist_items',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('watchlist_id', sa.Uuid(), nullable=False),
    sa.Column('company_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], name=op.f('fk_watchlist_items_company_id_companies'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['watchlist_id'], ['watchlists.id'], name=op.f('fk_watchlist_items_watchlist_id_watchlists'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_watchlist_items')),
    sa.UniqueConstraint('watchlist_id', 'company_id', name=op.f('uq_watchlist_items_watchlist_id'))
    )
    with op.batch_alter_table('watchlist_items', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_watchlist_items_watchlist_id'), ['watchlist_id'], unique=False)



def downgrade() -> None:
    with op.batch_alter_table('watchlist_items', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_watchlist_items_watchlist_id'))

    op.drop_table('watchlist_items')
    with op.batch_alter_table('financial_line_items', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_financial_line_items_period_id'))

    op.drop_table('financial_line_items')
    with op.batch_alter_table('watchlists', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_watchlists_owner_id'))

    op.drop_table('watchlists')
    with op.batch_alter_table('saved_valuations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_saved_valuations_owner_id'))

    op.drop_table('saved_valuations')
    with op.batch_alter_table('financial_periods', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_financial_periods_company_id'))

    op.drop_table('financial_periods')
    op.drop_table('users')
    op.drop_table('companies')
