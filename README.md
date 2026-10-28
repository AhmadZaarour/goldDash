# goldDash backend

FastAPI API for gold-shop catalog, purchases, barcoded inventory, supplier gold/USD
obligations, customer cash sales, returns, transfers, and cash reconciliation.
See [business rules and API contract](docs/business-rules.md) for endpoint details,
roles, amounts, and supported workflows.

## Local development

Requires Python 3.12 or 3.13, uv, Docker and Docker Compose.

```sh
uv sync --frozen
# Create .env from .env.example if it does not already exist.
docker compose up -d --wait
# Once: create the separate test database.
docker compose exec -T postgres createdb -U goldshop goldshop_test
uv run alembic upgrade head
uv run python -m app.cli  # Bootstrap the first administrator interactively.
uv run uvicorn app.main:app --reload
```

Set a random SECRET_KEY in your local .env; do not use the example placeholder.
No default administrator credentials are provided. Interactive API documentation
is served at `/docs`, and the machine-readable contract at `/openapi.json`.
`GET /health` checks the application; `/ready` checks PostgreSQL and Redis.

For a browser frontend, set CORS_ORIGINS to a JSON list of exact origins, for
example `["http://localhost:5173"]`. The default is an empty list. Bearer tokens
use the Authorization header; cross-origin cookies are not required.

## Verification

```sh
uv run pytest -q
uv run alembic check
```

Tests use TEST_DATABASE_URL and TEST_REDIS_URL, clear test state, and exercise
Alembic rather than create_all. Never point them at development/business data.
The migration replay test creates and drops a uniquely named temporary database;
the test PostgreSQL role needs CREATEDB. Coverage must remain at least 80%.

## Deployment

1. Use a managed/restricted PostgreSQL and Redis service or an equivalent private
   deployment. The provided Compose file is for development.
2. Supply DATABASE_URL, TEST_DATABASE_URL, REDIS_URL, TEST_REDIS_URL, a strong
   SECRET_KEY, DEBUG=false, and the frontend's exact CORS_ORIGINS through secure
   environment settings. Do not commit .env or production credentials.
3. Take a database backup and verify restoration before upgrades. Run
   `uv run alembic upgrade head` once as the release migration step, then
   `uv run alembic check`. Never use create_all for deployment.
4. Run `uv run uvicorn app.main:app --host 0.0.0.0 --port 8000` behind an HTTPS
   reverse proxy with request limits and login rate limiting. Use `/ready` for
   readiness and `/health` for liveness. Keep database/Redis ports private.
5. Schedule PostgreSQL backups with retention and restore drills. Keep Redis
   private; losing refresh-token state logs users out and does not lose business
   transactions. Do not downgrade migrations against live accounting data without
   a reviewed recovery plan and backup.

Printing, image hosting/uploads, supplier invoice return documents, and bank/cash
expense workflows are separate integrations. Images remain URL-only.
