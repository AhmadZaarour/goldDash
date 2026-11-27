"""Persist a shared default location."""

import sqlalchemy as sa

from alembic import op

revision = "j12026defaultlocation"
down_revision = "i12026manualquote"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "location_settings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("locations.id", ondelete="SET NULL")),
        sa.CheckConstraint("id = 1", name="ck_location_settings_singleton"),
    )


def downgrade():
    op.drop_table("location_settings")
