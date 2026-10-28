"""Run against a newly created disposable database, never the shop's database."""

import os
import secrets
import shutil
import signal
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from uuid import uuid4

import psycopg
from PIL import Image
from psycopg import sql
from sqlalchemy.engine import make_url

from app.core.config import settings
from app.core.security import hash_password

ROOT = Path(__file__).resolve().parents[2]
NPM = shutil.which("npm")
NODE = shutil.which("node")
if NPM is None or NODE is None:
    raise RuntimeError("Node and npm are required")


def wait_port(port, process):
    for _ in range(100):
        if process.poll() is not None:
            raise RuntimeError("Test server stopped; inspect the smoke-test log")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("Test server did not start")


url = make_url(settings.test_database_url)
name = f"goldshop_ui_test_{uuid4().hex[:12]}"
admin_url = url.set(drivername="postgresql", database="postgres").render_as_string(
    hide_password=False
)
with psycopg.connect(admin_url, autocommit=True) as admin, tempfile.TemporaryDirectory() as tmp:
    admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    backend = frontend = None
    try:
        password = secrets.token_urlsafe(24)
        env = dict(
            os.environ,
            DATABASE_URL=url.set(database=name).render_as_string(hide_password=False),
            DEBUG="false",
            SECRET_KEY=secrets.token_urlsafe(48),
            ITEM_IMAGE_DIR=tmp + "/images",
        )
        subprocess.run(  # noqa: S603 - fixed repository command, no user command input
            [str(ROOT / ".venv/bin/alembic"), "upgrade", "head"],
            cwd=ROOT,
            env=env,
            check=True,
            capture_output=True,
        )
        with psycopg.connect(
            url.set(drivername="postgresql", database=name).render_as_string(hide_password=False)
        ) as conn:
            conn.execute(
                "INSERT INTO users (email, username, password_hash, role, is_active) "
                "VALUES (%s,%s,%s,%s,true)",
                ("owner@example.com", "UI test owner", hash_password(password), "admin"),
            )
        photo = Path(tmp) / "piece.png"
        Image.new("RGB", (100, 100), "#c2a063").save(photo)
        log_dir = ROOT / "frontend/test-results" / name
        log_dir.mkdir(parents=True)
        with (
            (log_dir / "backend.log").open("w") as blog,
            (log_dir / "frontend.log").open("w") as flog,
        ):
            backend = subprocess.Popen(  # noqa: S603 - fixed repository executable
                [str(ROOT / ".venv/bin/uvicorn"), "app.main:app", "--port", "8001"],
                cwd=ROOT,
                env=env,
                start_new_session=True,
                stdout=blog,
                stderr=blog,
            )
            wait_port(8001, backend)
            frontend = subprocess.Popen(  # noqa: S603 - resolved local npm executable
                [NPM, "run", "dev", "--", "--port", "5175", "--strictPort"],
                cwd=ROOT / "frontend",
                env=dict(os.environ, API_PROXY_TARGET="http://127.0.0.1:8001"),
                start_new_session=True,
                stdout=flog,
                stderr=flog,
            )
            wait_port(5175, frontend)
            subprocess.run(  # noqa: S603 - fixed repository command, no user command input
                [NODE, "scripts/live-smoke.mjs"],
                cwd=ROOT / "frontend",
                env=dict(
                    os.environ,
                    UI_TEST_BASE="http://127.0.0.1:5175",
                    UI_TEST_EMAIL="owner@example.com",
                    UI_TEST_PASSWORD=password,
                    UI_TEST_PHOTO=str(photo),
                    UI_TEST_SCREENSHOT=str(log_dir / "workspace-ar.png"),
                ),
                check=True,
            )
    finally:
        for process in [frontend, backend]:
            if process is not None:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
        admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
