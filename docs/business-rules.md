# Backend business rules and API contract

## Roles and authentication

Only login, refresh, logout, health, readiness, and API documentation are public.
All business reads require a bearer token. Administrators create employee and
cashier accounts using `POST /api/v1/auth/register`; bootstrap administrators with
`python -m app.cli`. Anonymous signup is disabled.

| Operation | Roles |
| --- | --- |
| Read catalog, inventory, supplier balances/history | All authenticated users |
| Edit catalog, suppliers, locations, purities and products | Admin |
| Create purchases, bulk sales to suppliers, supplier settlements/reversals | Admin |
| Customer sales and item returns | Cashier or admin |
| Item/stock transfers, images and servicing | Employee or admin |
| Read cash entries and totals | Cashier or admin |
| Record/read cash reconciliations | Admin |

Customer creation/updates are available to authenticated staff. Purchase/sale
actors and creation timestamps come from the server, ignoring client values.
Inactive accounts cannot log in, refresh, or use existing access tokens. Refresh
tokens rotate atomically; logout revokes the refresh token. Access tokens expire
according to ACCESS_TOKEN_EXPIRE_MINUTES and are not revoked by logout alone.

## Supplier obligations and settlements

One purchase invoice belongs to one supplier. Every item line on it must name that
supplier. One item line means one physical, barcoded piece. Bulk sales are to
suppliers; customer sales use individual items. A purchase may contain multiple
purities, which remain separate in the supplier ledger.

Gold obligations are grams at the transaction's actual purity, without conversion
or netting across purities. Making charges are USD. Positive balances mean the
shop owes the supplier; negative balances mean the supplier owes the shop.
Purchases increase obligations; bulk sales decrease them.

- `GET /api/v1/suppliers/{id}/balance`: grams by purity ID and a separate USD balance.
- `GET /api/v1/suppliers/{id}/ledger`: immutable history, including invoice links,
  author, time, corrections and source keys. Filters: `purity_id`, `kind`,
  `from_at`, `to_at`; standard `limit`/`offset` pagination applies.
- `POST /api/v1/suppliers/{id}/settlements`: `idempotency_key`, `direction`
  (`sent` or `received`), `gold_grams`, `purity_id`, `making_usd`, `location_id`.
  Gold requires a purity. USD settlements are cash-only and require a drawer
  location. Sent amounts reduce supplier obligations; received amounts increase
  them. USD simultaneously posts to the cash drawer at that location.
- `POST /api/v1/suppliers/{id}/ledger/{entry_id}/reverse`: admin-only correction
  of a settlement, requiring `idempotency_key` and `reason`. It appends opposite
  supplier and cash entries rather than editing the original. Only one reversal
  per settlement is allowed. Invoice entries cannot be reversed this way.

Repeated settlement/reversal keys return 409; the frontend must not invent a new
key on an uncertain retry. It can inspect ledger history to find the original.
Settlements record gold accounting; physical gold deliveries must use inventory
workflows. Cash posting does not execute a real-world payment.

## Customer cash sales and reconciliation

`sell_price` is the final USD amount collected for that item. `discount` is
informational and is not subtracted a second time. Customer sales automatically
record the full cash receipt in the same transaction as the sale and inventory
changes. Partial customer payment is not supported. Optional `customer_id`
associates a known customer; omission represents a walk-in sale.

Item returns append cash refunds at the receiving location. Supplier USD cash
settlements and settlement reversals are included in the same cash ledger.

- `GET /api/v1/cash/entries?location_id=...`: paginated cash history with source links.
- `GET /api/v1/cash/summary?location_id=...`: customer receipts/refunds, supplier
  payments/receipts, supplier reversals, and net cash movement.
- `POST /api/v1/cash/reconciliations`: admin records a completed period using
  `idempotency_key`, `location_id`, `from_at`, `to_at`, `opening_usd`, `counted_usd`.
  Expected cash equals opening cash plus all recorded cash movement in that period;
  variance equals counted minus expected. Reconciliation records are immutable
  reports, not changes to the cash balance.
- `GET /api/v1/cash/reconciliations?location_id=...`: previous reports.

All times use ISO 8601 with a UTC offset. Time ranges are half-open:
`from_at <= created_at < to_at`. Reconciliations reject future or reversed periods.
Cash expenses, bank deposits and opening-balance corrections outside these
workflows are not yet supported; they must not be inferred from sales totals.

## Inventory, images, returns and transfers

The backend generates item barcodes: `GI` plus 16 uppercase hexadecimal characters.
The database enforces uniqueness and generation retries collisions. Legacy barcode
input in purchase requests is ignored. Existing codes are preserved through image
updates, transfers, returns and resale. Rendering and printing labels belong to
the frontend integration. Bulk stock has no barcode or image.

Individual purchase lines accept optional HTTP(S) `image_url` up to 2,048 characters.
`PATCH /api/v1/inventory/items/{id}/image` accepts `{"image_url": "https://..."}`
or `{"image_url": null}`. URLs are stored, not fetched; uploads remain out of scope.

Inventory reads:

- `/api/v1/inventory/items` and `/items/{id}` return barcode, state, location,
  image, purchase-line ID, product ID/name/SKU, category, purity, and weight.
- Item list filters: `q` (barcode/product name/SKU), exact `barcode`, `purchase_id`,
  `status` (`in_stock`/`sold`), `location_id`, `purity_id`, `category_id`.
  `sort=id` is the default; `sort=-id` reverses it.
- `/api/v1/inventory/stocks` and `/stocks/{id}` expose bulk purchase records.
  The list can filter `purchase_stock_id`.
- `/api/v1/inventory/movements` and `/movements/{id}` expose append-only item
  history; the list can filter `inventory_item_id`.
- Old item-only `/api/v1/inventory` and `/inventory/{id}` remain hidden aliases.

`POST /inventory/items/{id}/transfer` takes `location_id`. The item must be
available. `POST /inventory/returns` takes `sale_item_id`, `location_id`, and
`refund_usd`. A sold line can be returned once; its refund cannot exceed its final
sale price. The returned item becomes available for resale at the receiving
location. `POST /inventory/stocks/transfer` takes purity, source/destination
locations and placements, and positive weight. Both buckets change atomically,
and total weight is conserved. These paths all have the `/api/v1` prefix.

Sales lock items/balances, reject sold items, verify item locations and forbid
negative stock. Bulk purchases increment unique purity/location/placement buckets
atomically. Failed transactions roll back inventory, movements, and accounting.

## Lists, errors and retired endpoints

Catalog lists (`categories`, `goldpurities`, `locations`, `suppliers`, `customers`,
`products`) accept `q` and return arrays sorted by ID. Purchases and sales accept
`q` for invoice number and `location_id`. Lists use `limit` (1–100, default 50)
and `offset` (default 0), with `X-Total-Count`, `X-Limit`, and `X-Offset` headers.
Inventory, supplier history, and cash history use the same pagination convention.
Financial balance and cash DTOs serialize exact decimal values as JSON strings.
Database weights and charges use fixed-point storage. Clients must format amounts
explicitly and must not use floating-point arithmetic for accounting totals.

Errors use FastAPI's `detail` field: string for business errors and a validation
error array for invalid input. Statuses: 401 unauthenticated, 403 role/inactive
account, 404 absent record, 409 conflicting data/state or duplicate operation,
410 retired endpoint, 422 validation, 503 unavailable dependency. SQL and database
constraint details are not returned to clients.

`purchaseBook` and `saleBook` endpoints are retired and return 410. Their historic
database tables remain; no new code uses them for supplier accounting. Use the
supplier ledger and settlements exclusively.

## Deployment boundaries

The original corrective migrations target the disposable development schema, not
an arbitrary production database previously created with `create_all`. The cash
migration backfills historic customer item sales and refunds using the confirmed
cash rules. Older supplier settlements without drawer locations cannot be
reconstructed automatically. Audit/import those separately before production.

Supplier purchase returns and bulk-sale reversals need explicit return documents;
negative sale quantities and settlement reversals are not substitutes. This
release supports customer item returns and supplier settlement corrections.

## Frontend readiness corrections

### Retryable operations

`POST /purchases/item`, `/purchases/stock`, and `/inventory/stocks/transfer` now
require an `Idempotency-Key` header (1–100 characters, not blank), under `/api/v1`.
Generate a new key for each intentional operation. Retain the same key, request
data, and signed-in account when retrying after a timeout. Keys are scoped to the
user and operation. The original result and all business changes commit atomically;
a matching replay returns the original status/body, even if stock has since changed.
Reusing a key with different data returns 409. Failed transactions do not reserve
a key, so a corrected request may reuse it after a confirmed failure. Do not
silently drop this header in proxies or create a new key for an uncertain retry.
CORS permits this header for configured frontend origins.

### Product types and inactive records

Product `inventory_type` is either `item` or `bulk`. Item purchases accept only
item products, bulk purchases only bulk products. A product's type cannot change
after it has purchase references; create another product instead. The migration
rejects unknown legacy labels or incompatible purchase references rather than
guessing a mapping. Classify or split any such existing products explicitly before upgrading. It does not rewrite historic barcodes.

Supplier/location creation honors `is_active`. New purchases, sales and supplier
settlements require active trading entities. Transfers require active source and
destination locations, and returns require an active receiving location.
Historical reads and settlement reversals remain available for inactive entities.
Omitted PATCH fields preserve current values. Explicit null is rejected for
required fields; nullable fields such as customer phone and location address can
be cleared. Names and contact fields are validated against database lengths.

### Return, transfer and balance reads

Authenticated staff can read these paginated list/detail endpoints:

- `/api/v1/inventory/returns` and `/returns/{return_id}` include the sale, sale
  line, inventory item, location, refund, actor and timestamp.
- `/api/v1/inventory/transfers/items` and `/transfers/items/{transfer_id}` expose
  item transfer events. Item-transfer POST retains its item `id` and additionally
  returns `transfer_id` for opening the history detail.
- `/api/v1/inventory/transfers/stocks` and `/transfers/stocks/{transfer_id}` expose
  bulk transfer documents, including both locations/placements, purity and weight.

History lists support location, actor and offset-aware `from_at`/`to_at` filters;
returns additionally accept sale/line/item IDs, item transfers accept item and
from/to locations, and bulk transfers accept purity and source/destination
locations/placements. Use OpenAPI for exact parameter names. The standard
`limit`, `offset`, and pagination headers apply.

Sale-line reads now include `returned`, `return_id`, `refund_usd`, and `returned_at`.
A resale has a new sale line; a previous line's returned state stays attached to
that original sale. `/api/v1/balance` now supports standard pagination plus
`location_id`, `purity_id`, and `placement` (`factory`/`showroom`) filters.
