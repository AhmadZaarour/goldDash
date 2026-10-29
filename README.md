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

Printing, supplier invoice return documents, and bank workflows remain separate
integrations. Shop cash expenses and withdrawals are supported. Item photos can
use authenticated local uploads or an existing external image URL.

## Frontend

The bilingual English/Arabic React frontend is in [frontend](frontend/README.md).
Start the API, then run `npm ci && npm run dev` in `frontend/`. Printer integration
remains deferred. Phone photos use authenticated local storage; mount and back up
`ITEM_IMAGE_DIR` before deployment.

## Development data reset

To show the admin-only **Clear all development data** button at the bottom of
Overview, explicitly configure a disposable development installation and restart
the API:

```dotenv
APP_ENVIRONMENT=development
ENABLE_DEV_RESET=true
```

The button requires typing `CLEAR DEVELOPMENT DATA`. It deletes business records
(catalog, suppliers/customers, inventory, trades, settlements, cash history and
retry receipts) and generated uploaded item photos. It preserves all staff
accounts, login sessions and the migrated database schema. Stop other development
activity before resetting. Unrelated files in photo storage are preserved; a
cleanup warning is shown if any generated photos cannot be removed.

Reset is disabled by default and remains disabled when `APP_ENVIRONMENT` is
`production` or `test`, even if `ENABLE_DEV_RESET=true`. Do not enable it against
business data. This feature does not reset PostgreSQL/Redis services or delete
`.env` settings. No data is cleared merely by enabling or displaying the button.
