"""Allow workspaces to use a manually specified gold ounce quote."""

import sqlalchemy as sa

from alembic import op

revision = "i12026manualquote"
down_revision = "h12026prices"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("gold_price_settings", sa.Column("manual_ounce_usd", sa.Numeric(20, 6)))
    op.add_column("gold_price_settings", sa.Column("quote_updated_at", sa.DateTime(timezone=True)))
    op.create_check_constraint(
        "ck_gold_price_manual_ounce_positive", "gold_price_settings", "manual_ounce_usd > 0"
    )


def downgrade():
    op.drop_constraint("ck_gold_price_manual_ounce_positive", "gold_price_settings", type_="check")
    op.drop_column("gold_price_settings", "quote_updated_at")
    op.drop_column("gold_price_settings", "manual_ounce_usd")
