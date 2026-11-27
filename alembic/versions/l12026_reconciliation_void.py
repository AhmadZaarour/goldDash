"""Keep the original cash reconciliation when an admin voids it."""

import sqlalchemy as sa

from alembic import op

revision = "l12026reconciliationvoid"
down_revision = "k12026purchasecorrection"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("cash_reconciliations", sa.Column("voided_at", sa.DateTime(timezone=True)))


def downgrade():
    if op.get_bind().scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM cash_reconciliations WHERE voided_at IS NOT NULL)")
    ):
        raise RuntimeError("Voided reconciliations exist; restore a reviewed backup to downgrade")
    op.drop_column("cash_reconciliations", "voided_at")
