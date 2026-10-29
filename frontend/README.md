# GoldDash frontend

React + TypeScript + Vite interface for the existing FastAPI backend. English and
Arabic are available from the language switch; Arabic uses right-to-left layout.
Fonts are bundled locally. No external font or analytics service is required.

## Start

From the repository root, start PostgreSQL/Redis, apply migrations and bootstrap
an admin as described in the root README. Then run:

```sh
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

In another terminal:

```sh
cd frontend
npm ci
npm run dev
```

The development server proxies `/api` to the backend, so no CORS change is needed.
Set `API_PROXY_TARGET` for a different development backend address. For a separate
production API origin, set `VITE_API_BASE_URL` when building and configure the
backend's exact `CORS_ORIGINS`. Never put secrets in VITE-prefixed variables.

## First-release screens

- Login/logout and refresh-token rotation; account data is cleared on logout.
- Overview with actual inventory counts, supplier counts and location cash totals.
- Searchable inventory, photos, item/bulk transfers, returns and transfer history.
- Catalog creation/editing, including item/bulk product classification.
- Multi-piece purchases, supplier bulk purchases/sales, barcode-assisted customer
  checkout, sale details and item returns.
- Supplier balances, ledger history, cash/gold settlements and settlement reversal.
- Cash entries, expenses, owner withdrawals and reconciliation reports.
- Servicing and basic admin-only cashier/employee account creation.

Navigation and write controls respect admin/cashier/employee roles. The backend
remains the authority for permissions and business validation. Amounts are kept
as decimal strings; checkout calculations use decimal.js. Retryable operations
retain their key after network errors within the current page session. Keep the
form open and retry an uncertain purchase/transfer rather than creating a new one.
No printer commands or print-specific label templates are included.

## Photos

Cashiers/admins can use **Take / choose photo** in the item detail dialog. The
browser downsizes the image before upload; the backend validates and normalizes
it again, strips metadata and stores it in `ITEM_IMAGE_DIR` (default
`var/item-images`). JPEG, PNG and WebP are accepted; decoding other phone formats
depends on the browser. Uploaded images are served only to authenticated users.
External image URLs are still supported. Before production, mount ITEM_IMAGE_DIR
on persistent storage and include it in backups alongside PostgreSQL. HTTPS is
required for a secure phone/tablet deployment.

## Check

```sh
npm run build
npm test
npx playwright install chromium
npm run test:e2e
```

If Chromium is already installed, set `CHROMIUM_PATH` instead of downloading it.
Browser tests cover desktop/mobile navigation, Arabic RTL, and cashier visibility
using a mocked API. Backend tests exercise real database and photo behavior.

The additional **real API smoke test** creates a uniquely named temporary
PostgreSQL database, applies migrations, starts dedicated test servers, creates an
ephemeral admin, and uses the browser to perform catalog → purchase → photo → sale
→ expense. It drops that database and stops its own servers afterward:

```sh
# From the repository root; requires PostgreSQL CREATEDB privilege and ports 8001/5175.
CHROMIUM_PATH=/usr/bin/chromium PYTHONPATH=. .venv/bin/python frontend/scripts/live-smoke.py
```

It uses the test database connection settings and does not modify shop data.

## Production

Run `npm ci && npm run build`, serve `dist` over HTTPS, and configure an SPA
fallback to `index.html` for frontend routes. Proxy `/api` to FastAPI, preserve
Authorization and Idempotency-Key headers, and allow photo requests up to 11 MB
(the backend enforces a 10 MB source limit). See `nginx.conf.example` for the
routing shape; add your actual TLS/domain configuration. Browser support targets
current Chrome, Edge, Firefox and Safari. Chromium was exercised in this environment;
physical camera devices and Safari require device acceptance testing.

## Development reset button

Admins see **Development tools → Clear all development data** at the bottom of
Overview only when the backend explicitly enables the disposable development
reset. Set `APP_ENVIRONMENT=development` and `ENABLE_DEV_RESET=true` in the backend
and restart it. The typed confirmation clears business records and generated
photos while retaining staff accounts and login access. Canceling performs no
reset; successful reset reloads dashboard data. This control stays hidden when
disabled and is never shown to cashiers or employees. Backend guards apply even
to direct API calls. Keep it disabled outside disposable development systems.
