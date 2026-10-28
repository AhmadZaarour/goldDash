"A blank database must be deployable without importing the API or create_all."

import asyncio
import os
import subprocess
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from sqlalchemy.engine import make_url

from app.core.config import settings

PROJECT_ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_blank_database_upgrade_downgrade_and_replay():
    name = f"goldshop_migration_test_{uuid4().hex[:12]}"
    url = make_url(settings.test_database_url)
    admin_url = url.set(drivername="postgresql", database="postgres").render_as_string(
        hide_password=False
    )
    migration_url = url.set(database=name).render_as_string(hide_password=False)
    project = PROJECT_ROOT
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:

            async def migrate(*args):
                result = await asyncio.to_thread(
                    subprocess.run,
                    [str(project / ".venv/bin/alembic"), *args],
                    cwd=project,
                    env=dict(os.environ, DATABASE_URL=migration_url),
                    capture_output=True,
                    text=True,
                )
                assert result.returncode == 0, result.stderr

            await migrate("upgrade", "head")
            with psycopg.connect(
                url.set(drivername="postgresql", database=name).render_as_string(
                    hide_password=False
                )
            ) as conn:
                tables = {
                    row[0]
                    for row in conn.execute(
                        "SELECT tablename FROM pg_tables WHERE schemaname='public'"
                    )
                }
                assert {
                    "inventoryItems",
                    "purchases",
                    "sales",
                    "supplier_ledger_entries",
                    "item_returns",
                    "stock_transfers",
                } <= tables
            await migrate("check")
            await migrate("downgrade", "base")
            await migrate("upgrade", "171b0970514c")
            with psycopg.connect(
                url.set(drivername="postgresql", database=name).render_as_string(
                    hide_password=False
                )
            ) as conn:

                def row(query, values=None):
                    return conn.execute(query, values).fetchone()[0]

                user_id = row(
                    "INSERT INTO users (email, username, password_hash, role, is_active) "
                    "VALUES ('migration@example.com', 'migration', 'unused', 'employee', "
                    "true) RETURNING id"
                )
                location_id = row(
                    "INSERT INTO locations (name, code, is_active) VALUES ('Shop', 'SHOP', "
                    "true) RETURNING id"
                )
                category_id = row("INSERT INTO categories (name) VALUES ('Rings') RETURNING id")
                purity_id = row(
                    (
                        'INSERT INTO "goldPurities" (name, karat, purity) VALUES (%s, 24, 99.9) '
                        "RETURNING id"
                    ),
                    ("24K",),
                )
                supplier_id = row(
                    "INSERT INTO suppliers (name, phone, is_active) VALUES ('Supplier', "
                    "'123', true) RETURNING id"
                )
                product_id = row(
                    (
                        "INSERT INTO products (sku, name, category_id, purity_id, "
                        "inventory_type) VALUES ('RING', 'Ring', %s, %s, 'item') RETURNING id"
                    ),
                    (category_id, purity_id),
                )
                purchase_id = row(
                    (
                        "INSERT INTO purchases (created_by, location_id, supplier_id) VALUES "
                        "(%s, %s, %s) RETURNING id"
                    ),
                    (user_id, location_id, supplier_id),
                )
                purchase_line = row(
                    (
                        'INSERT INTO "purchaseItems" (supplier_id, purchase_id, product_id, '
                        "weight, gold_price_per_gram, gold_charge_in_grams, making_charge) "
                        "VALUES (%s, %s, %s, 1, 70, 1, 5) RETURNING id"
                    ),
                    (supplier_id, purchase_id, product_id),
                )
                item_id = row(
                    (
                        'INSERT INTO "inventoryItems" (purchase_item_id, location_id, barcode, '
                        "status) VALUES (%s, %s, %s, %s) RETURNING id"
                    ),
                    (purchase_line, location_id, "MIGRATION", "in_stock"),
                )
                sale_id = row(
                    "INSERT INTO sales (created_by, location_id) VALUES (%s, %s) RETURNING id",
                    (user_id, location_id),
                )
                sale_line = row(
                    (
                        'INSERT INTO "saleItems" (sale_id, inventory_item_id, '
                        "gold_price_per_gram, discount, sell_price) VALUES (%s, %s, 70, 5, 75) "
                        "RETURNING id"
                    ),
                    (sale_id, item_id),
                )
                conn.execute(
                    (
                        "INSERT INTO item_returns (sale_item_id, location_id, refund_usd, "
                        "created_by) VALUES (%s, %s, 25, %s)"
                    ),
                    (sale_line, location_id, user_id),
                )
            await migrate("upgrade", "head")
            with psycopg.connect(
                url.set(drivername="postgresql", database=name).render_as_string(
                    hide_password=False
                )
            ) as conn:
                assert dict(conn.execute("SELECT kind, amount_usd FROM cash_entries")) == {
                    "sale": Decimal("75.00"),
                    "refund": Decimal("-25.00"),
                }

            await migrate("check")
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
