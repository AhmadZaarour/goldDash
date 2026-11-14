# Vercel test deployment

Use two Vercel projects from this repository: the FastAPI backend at the repository
root, and the Vite frontend in `frontend/`. This guide is for a disposable demo
with test data. Printer integration remains deferred.

## Backend project

Import the repository as `golddash-api`, select FastAPI, and keep the root directory
at `./`. Leave install/build/output overrides unset. `pyproject.toml` explicitly
selects `app.main:app`; its Python requirement allows 3.12 and 3.13. Use the `test`
branch for the staging deployment. Verify the selected commit before deploying.

Set these variables on the backend project, in each environment you intend to use:

| Variable | Value |
| --- | --- |
| `APP_ENVIRONMENT` | `production` (also for the hosted demo) |
| `DEBUG` | `false` |
| `ENABLE_DEV_RESET` | `false` |
| `REPORT_TIMEZONE` | `Asia/Beirut` |
| `SECRET_KEY` | A unique randomly generated secret |
| `DATABASE_URL` | Neon PostgreSQL connection URL described below |
| `REDIS_URL` | Upstash TLS Redis URL described below |
| `CORS_ORIGINS` | JSON array containing the frontend's exact HTTPS origin |

Generate a signing secret locally with
`python3 -c "import secrets; print(secrets.token_hex(32))"` and paste it directly
into Vercel. Never commit credentials or use `VITE_` variables for backend secrets.
Do not configure test database/Redis URLs on the deployed API.

Neon: copy the **pooled** connection string and replace its initial
`postgresql://` with `postgresql+psycopg://`. Keep credentials, hostname, database,
and SSL/channel-binding parameters unchanged. The psycopg 3 driver is already a
dependency and supports this app's async engine. Vercel defaults to
`DATABASE_POOLING=false` to avoid keeping a SQLAlchemy connection pool per function
instance; Neon handles the shared pool. Outside Vercel the existing SQLAlchemy
pool remains enabled. Both defaults can be overridden by `DATABASE_POOLING`.

Upstash: use the TLS TCP connection URL, such as
`rediss://default:PASSWORD@HOST:PORT`, for `REDIS_URL`. REST URL/token variables from
the integration do not configure the existing redis-py client. Preserve TLS and
use database 0. Redis is required for refresh sessions, readiness, and the shared
30-second gold-price cache/cooldown. No cache bypass was introduced.

Use an exact origin in `CORS_ORIGINS`, for example
`["https://golddash-web.vercel.app"]`, without a trailing slash or URL path. Add
only trusted preview origins explicitly if needed. Redeploy after changing
environment variables. CORS permits GET, POST, PUT and PATCH with Authorization,
Idempotency-Key and X-Business-Unit headers.

## Private item photos

Create a Vercel Blob store with **Private** access, preferably near the backend,
and connect it to the **backend** project. Use a separate store for this demo;
avoid sharing production storage with previews or local tests.

If Vercel creates your project only when you first click Deploy, complete the
database initialization below and deploy the prepared API commit first. Then
connect the private Blob store and redeploy before testing photo workflows.
`/health` and `/ready` work without Blob credentials; photo operations return 503
until the store is configured.

The official `vercel-blob` SDK uses the connected `BLOB_STORE_ID` and Vercel OIDC
credentials. A `BLOB_READ_WRITE_TOKEN` in the hosting environment is also supported.
Keep it private and out of Git, frontend variables, and browser code. SDK credential
discovery reads process environment variables; placing only a token in this app's
local `.env` does not configure the SDK. For local Blob experiments, export its
credentials in the shell before launching the API.

On Vercel (`VERCEL=1`), `ITEM_IMAGE_STORAGE` defaults to `vercel_blob`. Elsewhere it
defaults to `local`, using `ITEM_IMAGE_DIR`. An explicit `ITEM_IMAGE_STORAGE` can
select either backend. Do not select local storage on Vercel: its function
filesystem cannot provide persistent photo storage.

Photos are normalized to JPEG, resized to 2048 pixels, stripped of EXIF metadata,
and stored under unique `items/<uuid>.jpg` paths. The database retains the existing
authenticated `/api/v1/media/items/<uuid>.jpg` links. Browser reads still check login,
workspace ownership and staged-upload ownership/expiry before fetching a private
blob. Store URLs and tokens are never returned to the browser. Responses are
`private, no-store`. Store outages return a generic 503; missing photos return 404.

All three camera/upload inputs resize and compress images below 4 MiB before
sending them through the API, beneath Vercel's 4.5 MB function payload limit.
The API also caps requests at 4 MiB on Vercel; oversized raw requests may be
rejected by the platform before reaching the API. Outside Vercel the existing
10 MiB raw upload limit remains. Neither setup accepts arbitrary file types.

Switching storage does not migrate existing local photo files. This fresh demo
database should start with new photos. A later storage migration must copy files
with their existing UUID names and verify reads before switching backends.

Expired, unattached uploads are cleaned up on subsequent photo uploads. A database
failure triggers deletion of the newly uploaded object. Cleanup failures are logged
without turning a committed operation into a failed request; a failed cleanup or
interrupted process can leave an orphan that requires later reconciliation. No
scheduled storage cleanup is configured. Development data reset remains local-only
and is disabled for Blob storage.

## Database initialization and first deployment

1. Use a trusted local terminal configured with this demo's backend environment
   variables. Keep hosted credentials separate from your ordinary development
   `.env`. The commands below target `DATABASE_URL`: inspect the selected host and
   database privately before executing them.
2. For migration/admin commands, use Neon's **direct** connection URL with the
   same `postgresql+psycopg://` prefix and SSL parameters. The deployed API keeps
   the pooled endpoint.
3. Run `uv sync --locked`, then `uv run alembic upgrade head` and
   `uv run alembic check` against that demo database.
4. Run `uv run python -m app.cli` interactively to create the first administrator.
   No default password or publicly exposed bootstrap endpoint is provided.
5. Deploy the prepared commit to Vercel. `/health` should return
   `{"status":"ok"}` and `/ready` should return `{"status":"ready"}`. The latter
   confirms database/Redis connectivity, not schema initialization; migrations are
   still a separate required step.
6. Create the frontend project with root `frontend/`, Vite, Node 24, build
   `npm run build`, output `dist`, and `VITE_API_BASE_URL` set to the backend's HTTPS
   origin (without `/api/v1`). `frontend/vercel.json` rewrites frontend routes to
   `index.html` so opening or refreshing a nested page works on Vercel.
7. Set the backend's exact `CORS_ORIGINS` to that frontend origin and redeploy.
   Check login/refresh, both workspaces, photo upload/read, gold-price settings
   updates, and a disposable purchase/sale before broader testing.

Do not run migrations at function startup or automatically in parallel preview
builds. Keep automated tests on their separate disposable local/CI databases;
never point tests at this deployed demo or business data. CI/CD deployment gating
is a separate step: this change does not connect GitHub CI to Vercel releases.

References: [FastAPI on Vercel](https://vercel.com/docs/frameworks/backend/fastapi),
[private Blob storage](https://vercel.com/docs/vercel-blob/private-storage),
[Python Blob SDK](https://pypi.org/project/vercel-blob/),
[function limits](https://vercel.com/docs/functions/limitations), and
[SQLAlchemy psycopg support](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#module-sqlalchemy.dialects.postgresql.psycopg).
