"""Track location and stock bucket for supplier settlements.

Revision ID: 6f08198a2d40
Revises: f39a31fe6bb9
"""

import sqlalchemy as sa

from alembic import op

revision = "6f08198a2d40"
down_revision = "f39a31fe6bb9"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("supplier_ledger_entries", sa.Column("location_id", sa.Integer(), nullable=True))
    op.add_column("supplier_ledger_entries", sa.Column("placement", sa.String(20), nullable=True))
    op.create_foreign_key(
        "fk_supplier_entry_location",
        "supplier_ledger_entries",
        "locations",
        ["location_id"],
        ["id"],
    )
    # Historical gold payments did not move stock; do not invent stock movements.
    op.execute("""UPDATE supplier_ledger_entries AS e SET location_id = c.location_id
                  FROM cash_entries AS c WHERE c.supplier_entry_id = e.id""")


def downgrade():
    op.drop_constraint("fk_supplier_entry_location", "supplier_ledger_entries", type_="foreignkey")
    op.drop_column("supplier_ledger_entries", "placement")
    op.drop_column("supplier_ledger_entries", "location_id")
