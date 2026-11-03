"""Snapshot 24K debt, configurable conversion factors and walk-in bulk purchases.

Historic ledger amounts and item costs remain unchanged. Equivalent debt is
backfilled once using the catalog purity at migration time.
"""

from alembic import op
import sqlalchemy as sa

revision = "a12026gold"
down_revision = "f8eb9aa823cc"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "goldPurities", "purity", type_=sa.Numeric(10, 6), postgresql_using="purity::numeric(10,6)"
    )
    op.add_column("goldPurities", sa.Column("repayment_factor", sa.Numeric(10, 6)))
    op.execute(
        """UPDATE "goldPurities" SET repayment_factor = CASE karat WHEN 18 THEN 0.74 WHEN 21 THEN 0.865 WHEN 24 THEN 1 ELSE purity / 100 END"""
    )
    # Confirmed factors for the standard karats. Historical entries below use these
    # definitions; their original grams, cash, stock movements and costs are preserved.
    op.execute(
        """UPDATE "goldPurities" SET purity = CASE karat WHEN 18 THEN 75 WHEN 21 THEN 87.5 WHEN 24 THEN 99.5 ELSE purity END"""
    )
    op.alter_column("goldPurities", "repayment_factor", nullable=False)
    op.execute("""INSERT INTO "goldPurities" (name, karat, purity, repayment_factor)
        SELECT '24K debt reference', 24, 99.5, 1 WHERE NOT EXISTS (SELECT 1 FROM "goldPurities" WHERE karat = 24)""")
    op.alter_column("supplier_ledger_entries", "gold_grams", type_=sa.Numeric(20, 6))
    for name, typ in [
        ("gold_24k", sa.Numeric(20, 6)),
        ("valuation_factor", sa.Numeric(14, 10)),
        ("physical_purity_id", sa.Integer()),
        ("physical_gold_grams", sa.Numeric(20, 6)),
        ("cash_gold_usd", sa.Numeric(14, 2)),
        ("gold_price_usd", sa.Numeric(14, 4)),
    ]:
        op.add_column("supplier_ledger_entries", sa.Column(name, typ))
    op.create_foreign_key(
        "fk_ledger_physical_purity",
        "supplier_ledger_entries",
        "goldPurities",
        ["physical_purity_id"],
        ["id"],
    )
    op.execute(
        """UPDATE supplier_ledger_entries e SET valuation_factor = CASE WHEN p.karat = 24 THEN 1 ELSE p.purity / 99.5 END FROM "goldPurities" p WHERE p.id = e.purity_id"""
    )
    op.execute(
        "UPDATE supplier_ledger_entries SET valuation_factor = 1 WHERE valuation_factor IS NULL"
    )
    op.execute(
        "UPDATE supplier_ledger_entries SET gold_24k = round(gold_grams * valuation_factor, 3)"
    )
    for name in ["gold_24k", "valuation_factor"]:
        op.alter_column("supplier_ledger_entries", name, nullable=False)
    op.add_column("purchaseItems", sa.Column("valuation_factor", sa.Numeric(14, 10)))
    op.alter_column("purchases", "supplier_id", nullable=True)
    op.add_column(
        "purchases", sa.Column("source", sa.String(20), nullable=False, server_default="supplier")
    )
    for name, typ in [
        ("total_gold_charge_grams", sa.Numeric(14, 3)),
        ("gold_debt_24k", sa.Numeric(20, 6)),
        ("paid_usd", sa.Numeric(14, 2)),
    ]:
        op.add_column("purchases", sa.Column(name, typ))
    op.add_column(
        "cash_entries",
        sa.Column("purchase_id", sa.Integer(), sa.ForeignKey("purchases.id"), unique=True),
    )
    op.drop_constraint("ck_cash_sources_outflows", "cash_entries", type_="check")
    op.create_check_constraint(
        "ck_cash_sources_outflows",
        "cash_entries",
        "(kind = 'sale' AND amount_usd >= 0 AND sale_id IS NOT NULL AND return_id IS NULL AND supplier_entry_id IS NULL) OR (kind = 'refund' AND amount_usd <= 0 AND return_id IS NOT NULL AND sale_id IS NULL AND supplier_entry_id IS NULL) OR (kind IN ('supplier_sent', 'supplier_received', 'supplier_reversal') AND supplier_entry_id IS NOT NULL AND sale_id IS NULL AND return_id IS NULL) OR (kind IN ('expense', 'withdrawal') AND amount_usd < 0 AND sale_id IS NULL AND return_id IS NULL AND supplier_entry_id IS NULL AND description IS NOT NULL AND length(trim(description)) > 0) OR (kind = 'customer_purchase' AND amount_usd < 0 AND purchase_id IS NOT NULL AND sale_id IS NULL AND return_id IS NULL AND supplier_entry_id IS NULL)",
    )
    op.create_check_constraint(
        "ck_cash_purchase_source",
        "cash_entries",
        "kind = 'customer_purchase' OR purchase_id IS NULL",
    )
    op.create_table(
        "purchase_photo_uploads",
        sa.Column("token", sa.String(32), primary_key=True),
        sa.Column("filename", sa.String(36), nullable=False, unique=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "inventory_item_id", sa.Integer(), sa.ForeignKey("inventoryItems.id"), unique=True
        ),
    )
    op.create_index(
        "ix_purchase_photo_uploads_expires_at", "purchase_photo_uploads", ["expires_at"]
    )


def downgrade():
    connection = op.get_bind()
    if connection.scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM purchases WHERE source = 'customer' OR total_gold_charge_grams IS NOT NULL) OR EXISTS (SELECT 1 FROM supplier_ledger_entries WHERE physical_gold_grams IS NOT NULL)"
        )
    ):
        raise RuntimeError("Cannot discard new accounting transactions; restore a reviewed backup")
    op.drop_table("purchase_photo_uploads")
    op.drop_constraint("ck_cash_purchase_source", "cash_entries", type_="check")
    op.drop_constraint("ck_cash_sources_outflows", "cash_entries", type_="check")
    op.drop_column("cash_entries", "purchase_id")
    op.create_check_constraint(
        "ck_cash_sources_outflows",
        "cash_entries",
        "(kind = 'sale' AND amount_usd >= 0 AND sale_id IS NOT NULL AND return_id IS NULL AND supplier_entry_id IS NULL) OR (kind = 'refund' AND amount_usd <= 0 AND return_id IS NOT NULL AND sale_id IS NULL AND supplier_entry_id IS NULL) OR (kind IN ('supplier_sent', 'supplier_received', 'supplier_reversal') AND supplier_entry_id IS NOT NULL AND sale_id IS NULL AND return_id IS NULL) OR (kind IN ('expense', 'withdrawal') AND amount_usd < 0 AND sale_id IS NULL AND return_id IS NULL AND supplier_entry_id IS NULL AND description IS NOT NULL AND length(trim(description)) > 0)",
    )
    for name in ["source", "total_gold_charge_grams", "gold_debt_24k", "paid_usd"]:
        op.drop_column("purchases", name)
    op.alter_column("purchases", "supplier_id", nullable=False)
    op.drop_column("purchaseItems", "valuation_factor")
    op.drop_constraint("fk_ledger_physical_purity", "supplier_ledger_entries", type_="foreignkey")
    for name in [
        "gold_24k",
        "valuation_factor",
        "physical_purity_id",
        "physical_gold_grams",
        "cash_gold_usd",
        "gold_price_usd",
    ]:
        op.drop_column("supplier_ledger_entries", name)
    op.alter_column("supplier_ledger_entries", "gold_grams", type_=sa.Numeric(14, 3))
    op.drop_column("goldPurities", "repayment_factor")
    op.alter_column("goldPurities", "purity", type_=sa.Float())
