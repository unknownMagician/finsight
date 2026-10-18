"""india market: instruments, company market/isin, period basis

Existing rows are SEC EDGAR data, so they are backfilled as market 'US' and basis
'unspecified'; nothing is dropped. Downgrade is lossy for Indian-market data only: it deletes
IN companies (and their instruments, periods, line items and watchlist entries) because the
0002 schema cannot represent them (CIK required, ticker globally unique).

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-18
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0003'
down_revision: str | None = '0002'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('instruments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('company_id', sa.Integer(), nullable=False),
    sa.Column('exchange', sa.String(length=10), nullable=False),
    sa.Column('symbol', sa.String(length=30), nullable=False),
    sa.Column('isin', sa.String(length=12), nullable=True),
    sa.Column('series', sa.String(length=10), nullable=True),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('listing_status', sa.String(length=30), nullable=False),
    sa.Column('provider', sa.String(length=100), nullable=False),
    sa.Column('provider_instrument_key', sa.String(length=100), nullable=True),
    sa.Column('last_traded_on', sa.Date(), nullable=True),
    sa.Column('former_symbols', sa.JSON(), nullable=False),
    sa.Column('retrieved_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], name=op.f('fk_instruments_company_id_companies'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_instruments')),
    sa.UniqueConstraint('exchange', 'isin', name=op.f('uq_instruments_exchange'))
    )
    with op.batch_alter_table('instruments', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_instruments_company_id'), ['company_id'], unique=False)
        batch_op.create_index('ix_instruments_exchange_symbol', ['exchange', 'symbol'], unique=False)

    # Existing companies all came from SEC EDGAR: backfill market='US', then drop the default
    # so new rows must state their market explicitly.
    with op.batch_alter_table('companies', schema=None) as batch_op:
        batch_op.add_column(sa.Column('market', sa.String(length=2), server_default='US', nullable=False))
        batch_op.add_column(sa.Column('isin', sa.String(length=12), nullable=True))
        batch_op.alter_column('ticker',
               existing_type=sa.VARCHAR(length=20),
               type_=sa.String(length=30),
               existing_nullable=False)
        batch_op.alter_column('cik',
               existing_type=sa.VARCHAR(length=10),
               nullable=True)
        batch_op.drop_constraint(batch_op.f('uq_companies_ticker'), type_='unique')
        batch_op.create_unique_constraint(batch_op.f('uq_companies_isin'), ['isin'])
        batch_op.create_unique_constraint(batch_op.f('uq_companies_market'), ['market', 'ticker'])
    with op.batch_alter_table('companies', schema=None) as batch_op:
        batch_op.alter_column('market', existing_type=sa.String(length=2), server_default=None)

    with op.batch_alter_table('financial_periods', schema=None) as batch_op:
        batch_op.add_column(sa.Column('basis', sa.String(length=20), server_default='unspecified', nullable=False))
        batch_op.drop_constraint(batch_op.f('uq_financial_periods_company_id'), type_='unique')
        batch_op.create_unique_constraint(batch_op.f('uq_financial_periods_company_id'), ['company_id', 'fiscal_year', 'fiscal_period', 'basis'])


def downgrade() -> None:
    # Remove Indian-market data explicitly (SQLite does not enforce ON DELETE CASCADE unless
    # foreign keys are enabled), so the 0002 constraints can be restored.
    in_companies = "SELECT id FROM companies WHERE market <> 'US'"
    op.execute(f"DELETE FROM financial_line_items WHERE period_id IN (SELECT id FROM financial_periods WHERE company_id IN ({in_companies}))")
    op.execute(f"DELETE FROM financial_periods WHERE company_id IN ({in_companies})")
    op.execute(f"DELETE FROM watchlist_items WHERE company_id IN ({in_companies})")
    op.execute(f"UPDATE saved_valuations SET company_id = NULL WHERE company_id IN ({in_companies})")
    op.execute(f"DELETE FROM instruments WHERE company_id IN ({in_companies})")
    op.execute("DELETE FROM companies WHERE market <> 'US'")

    with op.batch_alter_table('financial_periods', schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f('uq_financial_periods_company_id'), type_='unique')
        batch_op.create_unique_constraint(batch_op.f('uq_financial_periods_company_id'), ['company_id', 'fiscal_year', 'fiscal_period'])
        batch_op.drop_column('basis')

    with op.batch_alter_table('companies', schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f('uq_companies_market'), type_='unique')
        batch_op.drop_constraint(batch_op.f('uq_companies_isin'), type_='unique')
        batch_op.create_unique_constraint(batch_op.f('uq_companies_ticker'), ['ticker'])
        batch_op.alter_column('cik',
               existing_type=sa.VARCHAR(length=10),
               nullable=False)
        batch_op.alter_column('ticker',
               existing_type=sa.String(length=30),
               type_=sa.VARCHAR(length=20),
               existing_nullable=False)
        batch_op.drop_column('isin')
        batch_op.drop_column('market')

    with op.batch_alter_table('instruments', schema=None) as batch_op:
        batch_op.drop_index('ix_instruments_exchange_symbol')
        batch_op.drop_index(batch_op.f('ix_instruments_company_id'))

    op.drop_table('instruments')
