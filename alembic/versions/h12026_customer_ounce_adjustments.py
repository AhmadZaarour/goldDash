"""Customer ounce adjustments and immutable trade price snapshots."""

import sqlalchemy as sa

from alembic import op

revision = "h12026prices"
down_revision = "g12026weight"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "gold_price_settings",
        sa.Column("unit", sa.String(20), primary_key=True),
        sa.Column("buy_adjustment_usd", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("sell_adjustment_usd", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("unit IN ('factory', 'showroom')", name="ck_gold_price_unit"),
    )
    for table in ["purchases", "sales"]:
        op.add_column(table, sa.Column("market_ounce_usd", sa.Numeric(20, 6), nullable=True))
        op.add_column(table, sa.Column("ounce_adjustment_usd", sa.Numeric(12, 2), nullable=True))
        op.add_column(table, sa.Column("applied_ounce_usd", sa.Numeric(20, 6), nullable=True))


def downgrade():
    connection = op.get_bind()
    if connection.scalar(
        sa.text("""SELECT
        EXISTS (SELECT 1 FROM gold_price_settings) OR
        EXISTS (SELECT 1 FROM purchases WHERE market_ounce_usd IS NOT NULL) OR
        EXISTS (SELECT 1 FROM sales WHERE market_ounce_usd IS NOT NULL)
    """)
    ):
        raise RuntimeError(
            "Cannot downgrade after customer price activity; restore a backup instead"
        )
    for table in ["purchases", "sales"]:
        op.drop_column(table, "applied_ounce_usd")
        op.drop_column(table, "ounce_adjustment_usd")
        op.drop_column(table, "market_ounce_usd")
    op.drop_table("gold_price_settings")
