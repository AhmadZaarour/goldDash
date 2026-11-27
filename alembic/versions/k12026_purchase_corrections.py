"""Keep purchase cancellation audit and bulk stock provenance."""

import sqlalchemy as sa

from alembic import op

revision = "k12026purchasecorrection"
down_revision = "j12026defaultlocation"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("purchases", sa.Column("voided_at", sa.DateTime(timezone=True)))
    op.add_column("purchases", sa.Column("voided_by", sa.Integer(), sa.ForeignKey("users.id")))
    op.add_column("purchases", sa.Column("void_reason", sa.String(500)))
    op.add_column(
        "purchaseStocks",
        sa.Column("credited_balance_id", sa.Integer(), sa.ForeignKey("inventory_balances.id")),
    )
    op.add_column(
        "purchaseStocks", sa.Column("credited_balance_updated_at", sa.DateTime(timezone=True))
    )
    op.alter_column("inventory_balances", "updated_at", server_default=sa.text("clock_timestamp()"))


def downgrade():
    if op.get_bind().scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM purchases WHERE voided_at IS NOT NULL)")
    ):
        raise RuntimeError("Cannot downgrade with voided purchases; restore a reviewed backup")
    op.alter_column("inventory_balances", "updated_at", server_default=sa.text("now()"))
    op.drop_column("purchaseStocks", "credited_balance_updated_at")
    op.drop_column("purchaseStocks", "credited_balance_id")
    op.drop_column("purchases", "void_reason")
    op.drop_column("purchases", "voided_by")
    op.drop_column("purchases", "voided_at")
