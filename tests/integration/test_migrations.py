"""A blank database must be deployable without importing the API or create_all."""

import asyncio
import os
import subprocess
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
            await migrate("upgrade", "head")
            await migrate("check")
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
