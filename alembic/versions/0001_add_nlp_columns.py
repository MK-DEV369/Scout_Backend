"""Add classifier columns and embeddings table

Revision ID: 0001_add_nlp_columns
Revises: 
Create Date: 2026-04-30
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0001_add_nlp_columns'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # add classifier columns to event_records
    op.add_column('event_records', sa.Column('classifier_model', sa.String(length=200), nullable=True))
    op.add_column('event_records', sa.Column('classifier_confidence', sa.Float(), nullable=True))

    # create event_embeddings table
    op.create_table(
        'event_embeddings',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('event_id', sa.Integer(), nullable=False),
        sa.Column('embedding', sa.JSON(), nullable=True),
        sa.Column('cluster_id', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )


def downgrade():
    op.drop_table('event_embeddings')
    op.drop_column('event_records', 'classifier_confidence')
    op.drop_column('event_records', 'classifier_model')
