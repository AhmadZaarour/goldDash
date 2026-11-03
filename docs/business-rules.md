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
| Customer sales, item returns and walk-in bulk purchases | Cashier or admin |
| Item/stock transfers, images and servicing | Employee or admin |
| Read cash entries and totals | Cashier or admin |
| Record/read cash reconciliations | Admin |

Customer creation/updates are available to authenticated staff. Purchase/sale
actors and creation timestamps come from the server, ignoring client values.
Inactive accounts cannot log in, refresh, or use existing access tokens. Refresh
tokens rotate atomically; logout revokes the refresh token. Access tokens expire
according to ACCESS_TOKEN_EXPIRE_MINUTES and are not revoked by logout alone.

## Gold prices, purities and supplier obligations

Authenticated `GET /api/v1/gold-price` returns USD per ounce and per gram for
24K, 21K and 18K, `fetched_at`, provider `source_updated_at`, and `stale`.
The backend alone requests `https://api.gold-api.com/price/XAU`. Redis shares a
30-second successful-quote cache and upstream-attempt cooldown across workers.
Concurrent refreshes coalesce; failures also observe the cooldown. The last
successful quote is retained and explicitly marked stale on failure. A first
request during a refresh can return 503; clients retry after 30 seconds.
Redis failure returns 503 without contacting the provider. No browser requests
are made directly to the provider. Deployment egress must allow api.gold-api.com.

Prices: 24K gram = ounce / 31.1; 18K gram = 24K gram × 0.75 / 0.995;
21K gram = 24K gram × 0.875 / 0.995. Market quotes are suggestions, never
retroactive transaction prices. Manual settlement prices are authoritative.

Purity percentages are exact decimals (75 for 18K, 87.5 for 21K, 99.5 for
24K). `repayment_factor` is a separate configurable decimal fraction, defaulting
to 0.74 for 18K, 0.865 for 21K and 1 for 24K. Other karats default to their
purity percentage / 100 and may be configured explicitly. These commercial
repayment factors apply universally, including same-purity repayments.
Changing catalog settings does not recalculate completed transactions.

### Item purchase invoices

`POST /api/v1/purchases/item` is admin-only and requires `Idempotency-Key`.
Each line contains product, physical weight, purchase gold price per gram,
USD making charge and optional external image URL or staged `photo_token`.
There is no per-line gold-charge input. `total_gold_charge_grams` is required
and must equal the sum of the physical item weights; the frontend calculates it.

Debt is standardized to 24K equivalent: sum each line's weight × purity / 99.5
(24K weight uses factor 1), then round once to 0.001g, half up. This supports
mixed-purity invoices without adding unlike weights into a single conversion.
The invoice posts one gold debt plus its total USD making charges. Gold and USD
remain separate obligations. Positive balances mean the shop owes the supplier;
negative balances mean the supplier owes the shop.

The invoice's total physical gold charge is allocated among pieces in proportion
to fine-gold content for costing. Largest-remainder allocation at 0.001g keeps
the allocations nonnegative and their sum exact. Allocations are stored as each
piece's `gold_charge_in_grams` for accounting. The pricing-reference base cost
retains the test branch's formula: physical weight × (purchase gram price +
making charge). Historical purchase-line values remain unchanged.
Each new line stores the valuation factor used, and the invoice records both
its physical total and its standardized gold debt.

### Balances and settlements

`GET /api/v1/suppliers/{id}/balance` exposes authoritative `gold_24k`, separate
`making_usd`, and `is_settled` (both must be zero). The legacy
`gold_grams_by_purity` field describes nominal ledger history and must not be
used to calculate settlement status or spendable physical stock.

`GET /api/v1/suppliers/{id}/availability?location_id=...&placement=factory`
returns actual drawer cash and actual bulk stock by purity. Barcoded pieces
cannot fund bulk settlements. Only admins may settle accounts or query availability.

`POST /api/v1/suppliers/{id}/settlements` accepts:

- `idempotency_key`, `direction` (`sent` / `received`), `location_id`,
  `placement` (`factory` / `showroom`) and optional `close_account`.
- `purity_id` and `gold_grams`: the actual physical payment. The 24K debt
  credit is actual weight × that purity's commercial repayment factor.
- `cash_gold_usd`: cash substituted for gold debt. A positive amount requires
  `gold_price_usd`, the agreed USD per 24K-equivalent gram. Gold credit is
  cash / entered price. The UI suggests a fresh quote once and allows editing.
- `making_usd`: cash against the separate USD making-charge obligation.

Combined gold credit is rounded once to 0.001g, half up. Sent payments reduce
debt and stock/cash; received payments increase them. Actual cash moved is
`cash_gold_usd + making_usd`. The preview uses the same conversions and rounding
as the server. `close_account` requires exactly zero resulting gold and USD;
no silent debt write-off occurs. Partial and advance payments are allowed.

Stock checks use the selected physical purity, location and placement. Drawer
cash must cover sent cash. Location → supplier → stock locks prevent concurrent
overspending. Payment snapshots, supplier credit, stock and cash commit together.
Repeated settlement keys return 409; never invent a new key after an uncertain
response—inspect ledger history for the original payment.

`POST /api/v1/suppliers/{id}/ledger/{entry_id}/reverse` appends an opposite
ledger entry and restores the exact original physical gold and cash. It uses
recorded amounts and factors, never current settings or quotes. Only settlements
can be reversed, once each. Reversing received resources requires sufficient
remaining stock/cash. Historical payments retain their original resource behavior.

The migration preserves historical ledger grams, USD and item costs, and adds a
one-time 24K-equivalent snapshot. Original nominal entries remain visible.
Do not downgrade after new purchase/converted-settlement activity: downgrade
refuses to discard those payment snapshots. Use a reviewed backup restore.

### Walk-in customer bulk purchases

Admin/cashier `POST /api/v1/purchases/customer-stock` requires `Idempotency-Key`.
It takes `location_id`, bulk `product_id`, `placement`, positive `weight` and
`paid_usd`, with optional invoice number/notes. No customer identity is collected.
The purchase has `source=customer` and no supplier. Actual stock increases and
an immediate `customer_purchase` cash outflow is posted atomically. Insufficient
drawer cash rejects the entire purchase. Matching retries return the original
purchase; changed data with the same key returns 409.

Cash summary includes `customer_purchases_usd`; net cash and reconciliation
include the outflow. It is an inventory acquisition, not an operating expense
or supplier debt. Supplier bulk purchases continue to post supplier obligations.

### Photos while purchasing

Admin/cashier `POST /api/v1/purchases/photos` accepts raw JPEG/PNG/WebP bytes
using the existing 10 MB limit and normalization. It returns a `token` and
an authenticated preview URL. Tokens belong to the uploader and expire after
24 hours. Include a token on its purchase line; the transaction claims it once
and assigns its photo to the inventory item. Purchase replay retains the same
items and attachments. Expired unclaimed photos are cleaned in bounded batches
on later uploads. Canceling/removing a preview leaves an expiring temporary upload.

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
Shop expenses and drawer withdrawals are recorded through `/cash/outflows` as
described below. Bank deposits and unrelated opening-balance adjustments remain
unsupported; they must not be inferred from sales totals.

## Inventory, images, returns and transfers

The backend generates item barcodes: `GI` plus 16 uppercase hexadecimal characters.
The database enforces uniqueness and generation retries collisions. Legacy barcode
input in purchase requests is ignored. Existing codes are preserved through image
updates, transfers, returns and resale. Rendering and printing labels belong to
the frontend integration. Bulk stock has no barcode or image.

Individual purchase lines accept optional HTTP(S) `image_url` up to 2,048 characters.
`PATCH /api/v1/inventory/items/{id}/image` accepts `{"image_url": "https://..."}`
or `{"image_url": null}`. External URLs are stored, not fetched. Cashiers/admins can instead upload a phone
photo with `POST /api/v1/inventory/items/{id}/photo` (raw JPEG/PNG/WebP bytes,
maximum 10 MB). The backend normalizes it to JPEG, removes metadata, resizes it
and stores it in ITEM_IMAGE_DIR. `/api/v1/media/items/{filename}` requires a bearer
token; the frontend displays these through authenticated blob requests. Persistent
storage and image backups must be configured for deployment.

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

`POST /purchases/item`, `/purchases/stock`, `/purchases/customer-stock`, and `/inventory/stocks/transfer`
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


## Shop expenses and drawer withdrawals

`POST /api/v1/cash/outflows` is admin-only and requires `Idempotency-Key`.
Send `location_id`, `kind` (`expense` or `withdrawal`), positive `amount_usd`
(up to two decimal places), and a nonblank `description`; `category` is optional.
The drawer location must be active. Examples include packaging/rent as expenses
and owner cash removal as a withdrawal. Do not record supplier payments here:
their settlement endpoint already posts to the same cash ledger.

Both kinds create negative USD ledger entries, with the author and server time.
Matching retries return the original entry; a reused key with different data
returns 409. History includes description/category and accepts a `kind` filter.
Cash summaries expose positive `expenses_usd` and `withdrawals_usd` totals, and
subtract both from `net_usd`. Reconciliation includes them automatically, so
opening cash plus net movement matches the expected drawer cash. These records
log cash movements; they do not execute payments or modify supplier obligations.

## Monthly dashboard profit

Admin-only `GET /api/v1/insights/monthly-profit?month=YYYY-MM` optionally accepts
`location_id`. Omission includes all locations. Calendar boundaries use
`REPORT_TIMEZONE` (default `Asia/Beirut`); the end of the month is exclusive.
The frontend provides month/location filters in English and Arabic. The current
month includes transactions recorded so far. Empty months return zero totals;
expense-only months can show a loss.

Customer profit uses the **gold price recorded on each sale**, as agreed:

- Gold value = the piece's purchase `gold_charge_in_grams` × the sale's
  `gold_price_per_gram`. This values the supplier's gold obligation, including
  any gram charge, rather than using the original purchase gold price.
- Cost of a sold piece = that gold value + its purchase USD making charge.
- Net sales = final collected `sell_price` amounts − customer refunds.
  Discounts are already included in the collected amounts.
- Returns restore the original sale's gold valuation plus making cost in the
  **return month**. Prior months are unchanged; resale uses its own sale price.
  A return is attributed to the original sale location for profit reporting,
  even when the physical piece/refund is received at another location.
- Estimated net profit = net sales − sold costs + restored costs − shop expenses.
  Amounts are aggregated with Decimal/Numeric and rounded to cents, half up.

This is a customer-sale margin at sale-time gold valuation, after shop expenses,
not historical-cost accounting profit for the whole shop. Supplier purchases
(pieces and bulk) and bulk sales appear separately by purity, with booked grams
and USD making charges; they are not converted into customer profit. Their making
charges are booked trade amounts, not cash receipts or supplier-trading profit.
Supplier settlements, owner withdrawals, cash reconciliations and inventory
transfers do not count as operating profit/expenses. Cash expenses recorded as
`expense` are deducted regardless of supplier or customer activity.

## Disposable development reset

`GET /api/v1/development/reset-status` is admin-only and returns `enabled`.
`POST /api/v1/development/reset` requires an admin, `APP_ENVIRONMENT=development`,
`ENABLE_DEV_RESET=true`, and the exact JSON body
`{"confirmation":"CLEAR DEVELOPMENT DATA"}`. Disabled resets return 404;
unauthenticated requests return 401 and non-admins 403.

Reset truncates registered business tables together, restarts their sequences,
and preserves users, migrations and login sessions. No schema is dropped and no
`CASCADE` is used; unexpected external foreign keys or busy table locks reject
the transaction with 409. Photo cleanup happens only after database commit and
only removes snapshotted generated UUID `.jpg` files in `ITEM_IMAGE_DIR`, without
recursing into directories or deleting unrelated files. `photo_cleanup_complete`
reports whether this cleanup succeeded. A photo cleanup warning does not undo an
already committed business reset. The dashboard clears cached business results
and reloads the resulting empty state. Reset should run with no other development
activity; it does not lock out other browser sessions after completion.

## Barcoded piece base cost

Inventory item list/detail responses include read-only `base_cost_usd`, calculated
from the linked purchase line as `weight × (gold_price_per_gram + making_charge)`,
rounded to cents half up. This retains the pricing-reference formula already on
the test branch. It is separate from supplier debt and the monthly report's
sale-time gold valuation.

For example, a 10.000 g piece with a purchase gold price of $80/g and a making
charge value of $15 has a $950.00 base cost under this formula. The value is derived
rather than stored a second time.
It remains tied to the original purchase across transfers, sales, returns and
resale. Inventory lists/details and each selected customer-sale line show weight
and base cost for pricing reference. The final selling price remains explicitly
entered by the cashier. Monthly profit continues to use the sale-time gold
valuation selected for that report; this purchase-cost label does not change it.
