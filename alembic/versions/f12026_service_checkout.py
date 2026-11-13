"""Separate service intake and checkout, preserving legacy estimates and statuses."""

import sqlalchemy as sa

from alembic import op

revision = "f12026service"
down_revision = "e91357f0c122"
branch_labels = None
depends_on = None

OLD_CASH_CHECK = (
    "(kind = 'sale' AND amount_usd >= 0 AND sale_id IS NOT NULL AND return_id IS NULL AND "
    "supplier_entry_id IS NULL) OR (kind = 'refund' AND amount_usd <= 0 AND return_id IS "
    "NOT NULL AND sale_id IS NULL AND supplier_entry_id IS NULL) OR (kind IN "
    "('supplier_sent', 'supplier_received', 'supplier_reversal') AND supplier_entry_id IS "
    "NOT NULL AND sale_id IS NULL AND return_id IS NULL) OR (kind IN ('expense', "
    "'withdrawal') AND amount_usd < 0 AND sale_id IS NULL AND return_id IS NULL AND "
    "supplier_entry_id IS NULL AND description IS NOT NULL AND length(trim(description)) >"
    " 0) OR (kind = 'customer_purchase' AND amount_usd < 0 AND purchase_id IS NOT NULL AND"
    " sale_id IS NULL AND return_id IS NULL AND supplier_entry_id IS NULL) OR (kind IN "
    "('capital', 'adjustment', 'cash_transfer', 'internal_payment', 'production_cost') AND"
    " operation_id IS NOT NULL AND purchase_id IS NULL AND sale_id IS NULL AND return_id "
    "IS NULL AND supplier_entry_id IS NULL)"
)
NEW_CASH_CHECK = (
    "(kind = 'service_sale' AND amount_usd >= 0 AND sale_id IS NULL AND return_id IS NULL "
    "AND supplier_entry_id IS NULL) OR (kind = 'sale' AND amount_usd >= 0 AND sale_id IS "
    "NOT NULL AND return_id IS NULL AND supplier_entry_id IS NULL) OR (kind = 'refund' AND"
    " amount_usd <= 0 AND return_id IS NOT NULL AND sale_id IS NULL AND supplier_entry_id "
    "IS NULL) OR (kind IN ('supplier_sent', 'supplier_received', 'supplier_reversal') AND "
    "supplier_entry_id IS NOT NULL AND sale_id IS NULL AND return_id IS NULL) OR (kind IN "
    "('expense', 'withdrawal') AND amount_usd < 0 AND sale_id IS NULL AND return_id IS "
    "NULL AND supplier_entry_id IS NULL AND description IS NOT NULL AND "
    "length(trim(description)) > 0) OR (kind = 'customer_purchase' AND amount_usd < 0 AND "
    "purchase_id IS NOT NULL AND sale_id IS NULL AND return_id IS NULL AND "
    "supplier_entry_id IS NULL) OR (kind IN ('capital', 'adjustment', 'cash_transfer', "
    "'internal_payment', 'production_cost') AND operation_id IS NOT NULL AND purchase_id "
    "IS NULL AND sale_id IS NULL AND return_id IS NULL AND supplier_entry_id IS NULL)"
)


def upgrade():
    op.alter_column("inventoryServices", "customer_id", existing_type=sa.Integer(), nullable=True)
    op.add_column("inventoryServices", sa.Column("legacy_status", sa.String(50), nullable=True))
    op.execute("""UPDATE "inventoryServices" SET legacy_status = status,
        status = CASE WHEN lower(trim(status)) IN ('finished', 'completed', 'delivered', 'done')
        THEN 'finished' ELSE 'in_progress' END""")
    op.create_table(
        "service_sales",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("unit", sa.String(20), nullable=True),
        sa.Column(
            "service_id",
            sa.Integer(),
            sa.ForeignKey("inventoryServices.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("barcode", sa.String(50), nullable=False),
        sa.Column("notes", sa.String(200), nullable=True),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("locations.id"), nullable=False),
        sa.Column("amount_usd", sa.Numeric(14, 2), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("amount_usd >= 0", name="ck_service_sale_amount"),
    )
    op.create_index("ix_service_sales_unit", "service_sales", ["unit"])
    op.create_index("ix_service_sales_location_id", "service_sales", ["location_id"])
    op.create_index("ix_service_sales_created_at", "service_sales", ["created_at"])
    op.add_column("cash_entries", sa.Column("service_sale_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_cash_service_sale", "cash_entries", "service_sales", ["service_sale_id"], ["id"]
    )
    op.create_unique_constraint("uq_cash_service_sale", "cash_entries", ["service_sale_id"])
    op.drop_constraint("ck_cash_sources_outflows", "cash_entries", type_="check")
    op.create_check_constraint("ck_cash_sources_outflows", "cash_entries", NEW_CASH_CHECK)
    op.create_check_constraint(
        "ck_cash_service_source",
        "cash_entries",
        "(kind = 'service_sale' AND service_sale_id IS NOT NULL) OR "
        "(kind <> 'service_sale' AND service_sale_id IS NULL)",
    )


def downgrade():
    connection = op.get_bind()
    if connection.scalar(
        sa.text("SELECT EXISTS(SELECT 1 FROM service_sales)")
    ) or connection.scalar(
        sa.text('SELECT EXISTS(SELECT 1 FROM "inventoryServices" WHERE customer_id IS NULL)')
    ):
        raise RuntimeError("Cannot downgrade with new servicing activity; restore a backup instead")
    op.drop_constraint("ck_cash_service_source", "cash_entries", type_="check")
    op.drop_constraint("ck_cash_sources_outflows", "cash_entries", type_="check")
    op.create_check_constraint("ck_cash_sources_outflows", "cash_entries", OLD_CASH_CHECK)
    op.drop_constraint("uq_cash_service_sale", "cash_entries", type_="unique")
    op.drop_constraint("fk_cash_service_sale", "cash_entries", type_="foreignkey")
    op.drop_column("cash_entries", "service_sale_id")
    op.drop_table("service_sales")
    op.execute(
        'UPDATE "inventoryServices" SET status = legacy_status WHERE legacy_status IS NOT NULL'
    )
    op.drop_column("inventoryServices", "legacy_status")
    op.alter_column("inventoryServices", "customer_id", existing_type=sa.Integer(), nullable=False)
