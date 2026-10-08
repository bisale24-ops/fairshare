"""expense version and settlement author

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa


revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("expenses", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("settlements", sa.Column("created_by", sa.Integer(), nullable=True))
    op.execute("UPDATE settlements SET created_by = from_user")  # every old payment was recorded by the payer
    op.alter_column("settlements", "created_by", nullable=False)
    op.create_foreign_key("fk_settlements_created_by", "settlements", "users", ["created_by"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_settlements_created_by", "settlements", type_="foreignkey")
    op.drop_column("settlements", "created_by")
    op.drop_column("expenses", "version")
