"""Snapshot live gold prices for customer bulk purchases and all sales.

Existing prices are preserved; historical missing market prices remain null.
"""

import sqlalchemy as sa
from alembic import op

revision = "c12026prices"
down_revision = "b12026quote"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("sales", sa.Column("gold_quote_at", sa.DateTime(timezone=True)))
    for table in ["purchaseStocks", "saleStocks"]:
        op.add_column(table, sa.Column("gold_price_per_gram", sa.Numeric(14, 4)))


def downgrade():
    for table in ["purchaseStocks", "saleStocks"]:
        op.drop_column(table, "gold_price_per_gram")
    op.drop_column("sales", "gold_quote_at")
