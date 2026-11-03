"""Record the quote timestamp used to price a supplier item invoice."""

from alembic import op
import sqlalchemy as sa

revision = "b12026quote"
down_revision = "a12026gold"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("purchases", sa.Column("gold_quote_at", sa.DateTime(timezone=True)))


def downgrade():
    op.drop_column("purchases", "gold_quote_at")
