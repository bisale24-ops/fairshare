"""debt clock may be null

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa


revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("debt_state", "since", existing_type=sa.DateTime(timezone=True), nullable=True)


def downgrade() -> None:
    op.execute("DELETE FROM debt_state WHERE since IS NULL")
    op.alter_column("debt_state", "since", existing_type=sa.DateTime(timezone=True), nullable=False)
