"""Snapshot carrying value of physical supplier gold settlements.

Revision ID: e91357f0c122
Revises: 4e5b2163819a
"""
from alembic import op
import sqlalchemy as sa

revision = "e91357f0c122"
down_revision = "4e5b2163819a"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("supplier_ledger_entries", sa.Column("stock_value_usd", sa.Numeric(18, 4)))


def downgrade():
    op.drop_column("supplier_ledger_entries", "stock_value_usd")
