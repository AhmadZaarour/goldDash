"""Separate physical item weight from its snapshotted 24K-equivalent charge.

Backfill only invoices with complete recorded conversion factors and debt totals.
Original weights, historical charges, prices, cash and ledger entries are preserved.
"""

import sqlalchemy as sa
from alembic import op

revision = "d12026charge"
down_revision = "c12026prices"
branch_labels = None
depends_on = None

BACKFILL_SQL = """
WITH eligible AS (
    SELECT p.id, p.gold_debt_24k
    FROM purchases p JOIN "purchaseItems" i ON i.purchase_id = p.id
    WHERE p.gold_debt_24k IS NOT NULL
    GROUP BY p.id
    HAVING bool_and(i.valuation_factor IS NOT NULL)
       AND sum(i.weight * i.valuation_factor) > 0
), raw AS (
    SELECT i.id, i.purchase_id,
        round(e.gold_debt_24k * 1000) AS target_units,
        round(e.gold_debt_24k * 1000) * i.weight * i.valuation_factor
        / sum(i.weight * i.valuation_factor) OVER (PARTITION BY i.purchase_id) AS units
    FROM "purchaseItems" i JOIN eligible e ON e.id = i.purchase_id
), ranked AS (
    SELECT id, floor(units) AS whole_units,
        target_units - sum(floor(units)) OVER (PARTITION BY purchase_id) AS remainder,
        row_number() OVER (PARTITION BY purchase_id ORDER BY units - floor(units) DESC, id) AS rank
    FROM raw
)
UPDATE "purchaseItems" i
SET gold_charge_24k = (r.whole_units + CASE WHEN r.rank <= r.remainder THEN 1 ELSE 0 END) / 1000
FROM ranked r WHERE r.id = i.id AND i.gold_charge_24k IS NULL
"""


def upgrade():
    op.add_column("purchaseItems", sa.Column("gold_charge_24k", sa.Numeric(14, 3)))
    op.execute(BACKFILL_SQL)


def downgrade():
    op.drop_column("purchaseItems", "gold_charge_24k")
