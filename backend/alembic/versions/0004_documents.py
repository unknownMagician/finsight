"""documents and extracted facts

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-18
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0004'
down_revision: str | None = '0003'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:

    op.create_table('documents',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('owner_id', sa.Uuid(), nullable=False),
    sa.Column('company_id', sa.Integer(), nullable=True),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('doc_type', sa.String(length=30), nullable=False),
    sa.Column('fiscal_year', sa.Integer(), nullable=True),
    sa.Column('filename', sa.String(length=255), nullable=False),
    sa.Column('sha256', sa.String(length=64), nullable=False),
    sa.Column('size_bytes', sa.Integer(), nullable=False),
    sa.Column('page_count', sa.Integer(), nullable=False),
    sa.Column('pages_with_text', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], name=op.f('fk_documents_company_id_companies'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], name=op.f('fk_documents_owner_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_documents')),
    sa.UniqueConstraint('owner_id', 'sha256', name=op.f('uq_documents_owner_id'))
    )
    with op.batch_alter_table('documents', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_documents_company_id'), ['company_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_documents_owner_id'), ['owner_id'], unique=False)

    op.create_table('document_chunks',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('document_id', sa.Uuid(), nullable=False),
    sa.Column('page_number', sa.Integer(), nullable=False),
    sa.Column('chunk_index', sa.Integer(), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], name=op.f('fk_document_chunks_document_id_documents'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_document_chunks'))
    )
    with op.batch_alter_table('document_chunks', schema=None) as batch_op:
        batch_op.create_index('ix_document_chunks_document_page', ['document_id', 'page_number'], unique=False)

    op.create_table('document_facts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('document_id', sa.Uuid(), nullable=False),
    sa.Column('metric', sa.String(length=100), nullable=False),
    sa.Column('value', sa.Numeric(precision=28, scale=6), nullable=False),
    sa.Column('unit', sa.String(length=30), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=True),
    sa.Column('period_label', sa.String(length=50), nullable=True),
    sa.Column('period_end', sa.Date(), nullable=True),
    sa.Column('basis', sa.String(length=20), nullable=False),
    sa.Column('page_number', sa.Integer(), nullable=False),
    sa.Column('quote', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('verification_note', sa.String(length=300), nullable=True),
    sa.Column('model', sa.String(length=100), nullable=False),
    sa.Column('extracted_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], name=op.f('fk_document_facts_document_id_documents'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_document_facts'))
    )
    with op.batch_alter_table('document_facts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_document_facts_document_id'), ['document_id'], unique=False)

    op.create_table('document_pages',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('document_id', sa.Uuid(), nullable=False),
    sa.Column('page_number', sa.Integer(), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], name=op.f('fk_document_pages_document_id_documents'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_document_pages')),
    sa.UniqueConstraint('document_id', 'page_number', name=op.f('uq_document_pages_document_id'))
    )
    with op.batch_alter_table('document_pages', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_document_pages_document_id'), ['document_id'], unique=False)




def downgrade() -> None:

    with op.batch_alter_table('document_pages', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_document_pages_document_id'))

    op.drop_table('document_pages')
    with op.batch_alter_table('document_facts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_document_facts_document_id'))

    op.drop_table('document_facts')
    with op.batch_alter_table('document_chunks', schema=None) as batch_op:
        batch_op.drop_index('ix_document_chunks_document_page')

    op.drop_table('document_chunks')
    with op.batch_alter_table('documents', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_documents_owner_id'))
        batch_op.drop_index(batch_op.f('ix_documents_company_id'))

    op.drop_table('documents')

