"""Add summary_confidence column to event_records

Revision ID: 0002_add_summary_confidence
Revises: 0001_add_nlp_columns
Create Date: 2026-05-11
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0002_add_summary_confidence'
down_revision = '0001_add_nlp_columns'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('event_records', sa.Column('summary_confidence', sa.Float(), nullable=True))


def downgrade():
    op.drop_column('event_records', 'summary_confidence')
