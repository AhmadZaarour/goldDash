# Backend business rules and API contract

## Roles and authentication

Only login, refresh, logout, health, readiness, and API documentation are public.
All business reads require a bearer token. Administrators create employee and
cashier accounts using `POST /api/v1/auth/register`; bootstrap administrators with
`python -m app.cli`. Anonymous signup is disabled.

Sign in with your username or email. The login API accepts one of `identifier`,
`username`, or `email` alongside the password. The combined `identifier` field
gives a matching email priority. Use the explicit `username` field for an exact
username match.

| Operation | Roles |
| --- | --- |
| Read catalog, inventory, supplier balances/history | Cashier or admin |
| Edit catalog, suppliers, locations, purities and products | Admin |
| Create purchases, bulk sales to suppliers, supplier settlements/reversals | Admin |
| Customer sales, item returns and walk-in bulk purchases | Cashier or admin |
| Item/stock transfers and Showroom supply receipt | Admin |
| Inventory photos | Cashier or admin |
| Factory production and service intake/status | Employee or admin |
| Service checkout / service payment history | Cashier or admin |
| Service lookup | Any signed-in staff member |
| Read cash entries and totals | Cashier or admin |
| Record/read cash reconciliations | Admin |

Customer creation and updates are available to cashiers and admins. Purchase/sale
actors and creation timestamps come from the server, ignoring client values.
Inactive accounts cannot log in, refresh, or use existing access tokens. Refresh
tokens rotate atomically; logout revokes the refresh token. Access tokens expire
according to ACCESS_TOKEN_EXPIRE_MINUTES and are not revoked by logout alone.

## Gold prices, purities and supplier obligations

Authenticated `GET /api/v1/gold-price` returns USD per ounce and per gram for
24K, 21K and 18K, `fetched_at`, provider `source_updated_at`, `stale`, and
`quote_mode`. In live mode the backend requests
`https://api.gold-api.com/price/XAU`. Redis shares a
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
Each line contains product, physical weight, making charge in USD per physical gram and optional
external image URL or staged `photo_token`. Purchase gold price is server-calculated,
not an input. One active quote prices the entire invoice. Each line
uses USD per 24K gram × its purchase valuation factor, rounded to four decimal
places half up. The invoice stores `gold_quote_at` and each piece retains its
calculated `gold_price_per_gram`. Stale/unavailable quotes return 503 with no
partial invoice, inventory or ledger entry. A successful idempotent replay returns
the original purchase and never fetches another quote or reprices it.
There is no per-line gold-charge input. `total_gold_charge_grams` is required
and must equal the sum of the physical item weights; the frontend calculates it.

Debt is standardized to 24K equivalent: sum each line's weight × purity / 99.5
(24K weight uses factor 1), then round once to 0.001g, half up. This supports
mixed-purity invoices without adding unlike weights into a single conversion.
The invoice posts one gold debt plus the sum of each line’s physical weight × its USD/g making rate,
rounded once to USD cents, half up. Gold and USD
remain separate obligations. Positive balances mean the shop owes the supplier;
negative balances mean the supplier owes the shop.

Each new piece keeps its own physical weight as `gold_charge_in_grams`; physical
weights at different purities are never redistributed between pieces. The separate
`gold_charge_24k` field records its converted debt contribution. Largest-remainder
allocation applies only to the final 0.001g invoice rounding in this common 24K
unit, so per-piece 24K charges add exactly to the invoice's booked 24K debt.
For example, 5g of 21K plus 2.5g of 18K records 4.397g and 1.884g of 24K-equivalent
charge, totaling 6.281g. Physical weights remain 5g and 2.5g; the 21K piece must
never be relabeled as a 5.25g physical charge.

The acquisition cost uses physical weight × (purchase gram price + making charge).
Sale-time pricing uses the current quote. New sale-time reporting uses the recorded
physical charge and matching sale gram rate. Historical prices, original charge
fields, cash and ledger entries remain unchanged. The migration adds explicit 24K
charges to prior invoices only where complete saved line conversion factors and
an invoice debt snapshot exist, using those saved values rather than current
catalog settings. Earlier history without enough evidence keeps a null 24K charge.
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

### Walk-in customer bulk purchases and opening stock

Admin/cashier `POST /api/v1/purchases/customer-stock` requires `Idempotency-Key`.
It takes `location_id`, bulk `product_id`, `placement`, positive `weight` and
nonnegative `paid_usd`, with optional invoice number/notes. No customer identity
is collected. Negative payments are rejected. A zero payment records
`source=opening`: opening bulk stock with no supplier debt, no cash entry and no
drawer-funds requirement. It uses the same atomic inventory/retry safeguards as
a paid purchase, including when the starting drawer and stock balances are zero.
A positive-payment purchase has `source=customer` and no supplier. Actual stock increases and
an immediate `customer_purchase` cash outflow is posted atomically. Insufficient
drawer cash rejects the entire purchase. Matching retries return the original
purchase; changed data with the same key returns 409.

Cash summary includes `customer_purchases_usd`; net cash and reconciliation
include the outflow. It is an inventory acquisition, not an operating expense
or supplier debt. Supplier purchases are item invoices only. Physical bulk
repayment is recorded through supplier settlements, never as another purchase.
`POST /api/v1/purchases/stock` is retired (410, omitted from OpenAPI). Historical
supplier bulk invoices remain readable through the existing purchase/stock GETs.

### Photos while purchasing

Admin/cashier `POST /api/v1/purchases/photos` accepts raw JPEG/PNG/WebP bytes
with normalization and a 10 MiB limit locally (4 MiB on Vercel). It returns a `token` and
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

New item barcodes use `GI` followed by eight uppercase Crockford Base32 characters.
The database enforces uniqueness and generation retries collisions. Legacy barcode
input in purchase requests is ignored. Existing codes are preserved through image
updates, transfers, returns and resale. Rendering and printing labels belong to
the frontend integration. Bulk stock has no barcode or image.

Individual purchase lines accept optional HTTP(S) `image_url` up to 2,048 characters.
`PATCH /api/v1/inventory/items/{id}/image` accepts `{"image_url": "https://..."}`
or `{"image_url": null}`. External URLs are stored, not fetched. Cashiers/admins can instead upload a phone
photo with `POST /api/v1/inventory/items/{id}/photo` (raw JPEG/PNG/WebP bytes,
maximum 10 MiB locally, 4 MiB on Vercel). The backend normalizes it to JPEG,
removes metadata, resizes it and stores it in ITEM_IMAGE_DIR locally or private
Vercel Blob storage. `/api/v1/media/items/{filename}` requires a bearer token and
the owning workspace; an unclaimed staged upload also requires its creator and an
unexpired token. The frontend displays these through authenticated blob requests.
All camera inputs resize/compress uploads below 4 MiB. Configure persistent storage
and image backups for deployment; see [Vercel setup](vercel-deployment.md).

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

`POST /purchases/item`, `/purchases/customer-stock`, and `/inventory/stocks/transfer`
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
- Cost of a sold piece = that gold value + physical purchase weight × its USD/g making rate.
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

The customer sale form calculates each selected piece's base cost from the
active customer selling quote and the piece's making charge. Supplier-purchased
pieces use physical weight × the current gram rate for their purity, plus the
piece's total making charge. Pieces received from production use their
24K-equivalent weight and the current 24K gram rate. The form rounds the result
to cents. This calculated amount is a pricing reference and is never saved.
The cashier enters the final selling price.
`GET /api/v1/inventory/items/{id}/sale-cost` supplies the calculation inputs.

The inventory item detail retains the acquisition-cost reference in
`base_cost_usd`. Older purchases without an acquisition snapshot use
physical weight × (purchase gram price + making rate), rounded to cents half up.
Accounting and profit reports continue to use their existing saved amounts and
the applicable valuation method.

## Live per-gram rates on every new trade

All supported purchases and sales use the same server-side rate calculation.
One active quote is used for an entire invoice, with USD per physical gram rounded
to four decimal places, half up:

| Purity | USD per gram |
| --- | --- |
| 24K | ounce USD / 31.1 |
| 21K | (ounce USD / 31.1) × 0.875 / 0.995 |
| 18K | (ounce USD / 31.1) × 0.75 / 0.995 |

Configured purity percentages drive the non-24K factors. Commercial repayment
factors (0.74 and 0.865) remain separate; they are never market-price factors.
All flows share the existing 30-second Redis cache and failure cooldown.

- Supplier item purchases retain their automatic line rates and invoice quote time.
- Customer bulk purchases and zero-USD opening stock record market
  `gold_price_per_gram` on the stock line and `gold_quote_at` on the invoice.
  `cost_per_gram` remains actual USD paid / physical weight. The market rate does
  not overwrite `paid_usd`, create additional cash movements, or create debt.
- Customer item sales no longer accept an input gram rate. Each line gets its
  inventory piece's purity rate from the sale's one quote. `sell_price` and
  informational `discount` remain manually entered; the cash receipt uses the
  sum of entered final prices. Monthly profit uses the recorded sale-time rates.
- Supplier bulk sales record `gold_price_per_gram` on the stock sale line and
  `gold_quote_at` on the invoice. Stock movements, gold obligations and entered
  making charges retain their existing behavior; the quote does not create a
  cash receipt or convert the gold obligation to USD.

The forms show read-only live previews. The server snapshots the current quote on
confirmation and ignores client-provided gram-rate overrides. Stale/unavailable
quotes reject the new trade atomically, including opening stock; no partial
invoice, stock, sale, cash or ledger changes persist. Successful purchase retries
return the original recorded rate without fetching a new quote.

Completed purchases/sales, returns and reports never recalculate against current
quotes. New nullable bulk-rate/timestamp columns leave historical missing market
rates null rather than infer them from paid cost or today's quote. Existing item
purchase/sale prices are preserved. Retired supplier bulk-purchase endpoints remain
retired, with their history readable.


## Independent Factory and Showroom workspaces

Each request selects `X-Business-Unit: showroom` (default) or `factory`. Cash,
stock quantities and carrying values, pieces, purchases, sales, expenses,
reconciliations and external supplier accounts are owned by that workspace.
Locations, contacts and product/purity catalogs remain shared. A location is a
physical address. Workspace access follows the account role. Cashiers work in
Showroom. Employees work in Factory and have access to Production, Servicing,
and the location and purity lookups those screens need. Admins can work in
either workspace and review unassigned history. A workspace switch clears
browser data before loading the selected workspace.

Showroom purchases supplier pieces individually, incurs gold debt in 24K-equivalent
grams plus USD making charges, and sells pieces to customers. Factory creates
production batches and sells finished gold by purity and weight to suppliers or Showroom.
Factory does not enter or barcode individual pieces. Both units
can buy bulk from walk-in customers with immediate payment, including the existing
zero-USD inventory entry. No customer identity or supplier debt is created by bulk
purchases. The bulk-buy form automatically uses the active workspace's bucket.

### Opening balances and capital

Admins use **Opening balances** for each workspace/location: record cash and one
or more physical gold weights, purity, total recorded USD carrying value, date
and notes. A carrying value of zero must be entered explicitly if appropriate.
This records resources already owned; it does not spend cash, create revenue or
incur supplier debt. Opening is allowed once at a location with no active cash or
bulk balances. Subsequent capital additions and signed corrections are separate,
audited actions. Corrections cannot spend unavailable cash or gold. The stock
valuation action records a reviewed carrying value for existing bulk, including
historical stock whose cost is unknown. Capital is never operating profit.

### Production and cost

Factory tracks raw bulk, work in progress and finished gold separately. Start a batch
with valued raw weights by purity at one location; the weights and carrying values
are removed from available raw stock and held in the batch. A default 24K input
works alongside mixed-purity inputs. No product selection, piece count or barcode
is required. Production does not require a market quote.

Record named steps as work proceeds. Each step records **all remaining work** by
purity, newly recovered scrap (excluding scrap from earlier steps), optional direct
cash costs and notes. Input for the first step is the starting gold; later steps
consume the preceding step's remaining output. Physical weights can increase when
alloy is added: comparisons use purchase purity factors in 24K equivalent, never
commercial repayment factors. Factors are saved on first use of each purity in the
batch. Gold quantities for the audit use six decimal places. Gold gains above
0.000001g are rejected; loss above 0.001g requires an explanation. A step version
prevents two staff members from recording against the same preceding measurement.

Finishing releases only the last step's output as finished stock by purity and
returns accumulated scrap to raw stock. Recovered scrap retains its proportional
input carrying value. Remaining material value, loss and paid direct costs are
allocated to finished output by 24K content. Direct costs reduce Factory cash once
and remain capitalized in the stock value. Raw input, step costs and final release
are idempotent and atomic. Finished stock is consumed FIFO with proportional saved
carrying values; reservations and sales cannot overspend a weight bucket.

Admins can correct an in-progress batch or an unused finished batch through the
production reversal, restoring input values and paid costs. After its finished
gold has been sold or supplied, the dependent supply must be reversed first.
**Factory gold inventory** also supports explicit finished opening weights and
carrying values (including zero); these create capital stock, not profit or cash.
Unused finished opening entries can be reversed from opening-balance history.

### Internal supply and payment

An admin supplies Showroom using one weight and making-charge-per-physical-gram
line per purity, destination and agreed USD per 24K-equivalent gram (live quote
suggested, manual price applied). The factory weight is consumed immediately and
recorded as pending Showroom stock. One shared gold/USD account represents Factory's
receivable and Showroom's payable, separate from external suppliers.

Showroom employees/admins register individual received pieces against the invoice,
choosing products, weights and optional photos. Partial receipt is allowed; each
purity's total weight cannot exceed the unregistered balance. New piece barcodes
are generated on receipt. Their acquisition value is the agreed internal value;
the original company production cost is preserved separately for combined profit.
A weighted supply can be reversed while no received pieces have been registered.
Existing piece-based supply history retains its earlier reversal rules.

Payments move actual gold and/or cash between the two workspaces atomically.
Acquisition gold remains `18K weight × 0.75 / 0.995` or
`21K weight × 0.875 / 0.995`. Repayment remains `24K debt / 0.74` for 18K,
or `/ 0.865` for 21K. Thus physical gold clears debt at weight × its saved
repayment factor. Cash substitution uses the entered USD per 24K-equivalent gram.
Gold quantity and carrying cost travel together. Full settlement requires both
gold and USD balances to reach zero. Internal invoices and payments have audited
reversals using original factors/costs; invoices cannot reverse after external
sale history. Ordinary cash/gold transfers move resources without clearing debt.

Factory supplier sales have multiple purity lines: physical weight and USD making
charge per physical gram. The invoice's total making charge is rounded once to
cents and allocated across its lines. New sales use a fresh server quote with a
saved 24K rate. They consume only finished weight, create canonical 24K-gold/USD
receivables, and create no cash receipt until settlement. Supplier settlements use the same existing repayment equations.
Received supplier gold is valued from the entered 24K USD rate or the fresh shared
quote, with carrying value saved for production and exact reversal. A reversal
never uses today's quote or edited purity settings.

### Profit reports

**Workspace reports** use recorded acquisition/production costs. Factory includes
its internal sale margin; Showroom uses its agreed internal acquisition cost for
customer sales. Combined business profit excludes internal invoices and uses
original company costs when an external sale occurs, so unsold internal markup
never becomes company profit. Returns restore original sale cost snapshots.
Only operating expenses reduce these margins; capital, transfers and settlements
do not. A missing historical carrying cost makes affected profit unavailable.
The older Showroom monthly trade-margin panel remains a distinct sale-time gold
valuation view; it is not the recorded-cost workspace profit report.

### Historical cutover and API

The original workspace migration leaves pre-workspace records unassigned (`unit IS NULL`), readable
through the admin **Unassigned history** workspace. No placement-based ownership
is inferred. Admins explicitly assign purchases (including linked inventory,
receipts and supplier ledger), sales (including cash and ledger), cash, pieces,
bulk balances and supporting history. Linked conflicting ownership rejects the
assignment. Review remaining categories after assigning invoice roots; historic
aggregate bulk balances are classified explicitly rather than reconstructed.
Avoid seeding the same resources again after assigning existing balances.

The weight migration `g12026weight` converts available, already-owned Factory
pieces into finished-weight lots while retaining original piece, barcode, batch
and invoice records. Those pieces are marked `weight_stock` to prevent counting
or selling their gold twice. Their owner/company costs and physical weights are
preserved; neither Showroom pieces nor unassigned history is converted. After new
weight activity, downgrade refuses to discard the new records.

Apply `alembic upgrade head` before starting this version. The workspace migration
refuses downgrade after workspace activity. No business database data is modified
by installing the application code alone.

New routes under `/api/v1/operations` include `overview`, `opening`, `capital`,
`adjustments`, `stock-value`, `cash-transfers`, `gold-transfers`, `history`,
`production`, `internal-invoices`, `internal-payments`, `internal-balance`,
`internal-resources`, `supplier-item-sales`, `profit`, `legacy`, `legacy/assign`
and `staff`. Financial writes require `Idempotency-Key` and preserve original
results on retries. Factory staff can record production; financial administration
and cross-workspace transfers require admin. Reports use Asia/Beirut month bounds.


## Per-gram purchase making charges and service organization

For supplier item purchases, `making_charge` is a **USD per physical gram** rate.
A 10g piece at $80/g gold and $5/g making has a $850 cost and creates $50 of
making debt. Invoice USD making debt sums `weight × making_charge` across all
pieces and rounds once to cents, half up. Piece costs, historical cost fallbacks,
monthly trade margins and return cost restoration apply the same physical weight.
The purchase form and details label the rate USD/g; the form previews its USD total.
Settlement `making_usd`, internal invoice making amounts and production direct
costs are already total USD amounts. Their meaning is unchanged.

Existing posted ledger entries and saved acquisition/sale cost snapshots are not
rewritten by this code update. Historical records without cost snapshots derive
costs using the purchase making rate. Any correction to previously posted debt
requires a separately reviewed accounting correction.

`api/v1/operations.py` and `api/v1/supplier_ledger.py` handle HTTP parameters,
authorization and response models. DTOs live in `schemas/operations.py` and
`schemas/supplier_ledger.py`. Workspace queries live in
`services/operations_query_service.py`; transactions and idempotent completion
remain in `services/operations_service.py`. Supplier balance/settlement/reversal
logic is in `services/supplier_ledger_service.py`. Financial writes keep their
existing locks, atomic commits, resource checks and saved retry results.


## Camera barcode lookup

Scanning selects an inventory piece or service record; it does not post a sale,
refund, service job or cash movement. Customer-sale lookup remains exact, limited
to `in_stock` pieces at the chosen location in the active workspace. A duplicate
scan retains the existing sale line and its manually entered price. Missing stock
is reported without adding a piece.

`GET /api/v1/servicing?barcode=...` optionally filters service records by exact
barcode (1–50 characters). Query parameters support reserved characters such as
slashes without changing identifiers. Existing unfiltered service lists and
barcode-path reads retain their behavior. Workspace and role checks remain in
force. Staff explicitly save edits and cashiers explicitly submit payment after scanning.


## Service intake and checkout

Service intake accepts optional notes (200 characters maximum) and `in_progress`
(default) or `finished` status. New service barcodes use `SV` followed by eight
uppercase Crockford Base32 characters. The database enforces uniqueness and
generation retries collisions. Creation uses
`Idempotency-Key`, so a lost response can be retried without creating another job.

Admins create and update jobs in either workspace. Employees handle Factory jobs.
Staff can look up jobs in the workspace their role allows. Cashiers collect
payments for Showroom jobs. Admins can collect payments in both workspaces.
Checkout uses `POST /servicing/sales`, sending
barcode, active location and `cost` (the amount collected in USD, not an expense).
The amount must be nonnegative and have at most two decimal places. No gold price
is needed. A job must be finished and unpaid. Location and job locks serialize
checkout; a unique service-sale link and unique cash source prevent duplicates.
Checkout uses a saved idempotent response and commits sale, receipt and cash entry
atomically. Paid service records cannot be edited or reopened.

Service receipts increase the selected workspace/location's cash drawer using
`service_sale` entries. Summaries show `service_received_usd`; monthly reports
include service income once on the collection date, including company reports.
No service cost is inferred from the amount collected: costs remain separately
recorded operating expenses. Service income is broken out from item revenue.

Migration `f12026service` makes old customer links optional, preserves barcodes and
legacy cost estimates, and saves original statuses in `legacy_status`. Statuses
finished/completed/delivered/done (ignoring case/outer whitespace) become finished;
other statuses become in_progress. It does not infer historical payments or create
cash receipts from estimates. Downgrade refuses to discard new checkout/intake
activity. Deploy with `alembic upgrade head` before running the updated app.


### Weight workflow API

New endpoints under `/api/v1/operations`:

- `POST weight-production`: reserve raw input and open a weight batch.
- `POST weight-production/{id}/steps`: save name, outputs, new scrap, paid costs,
  notes and `expected_step` (the current number of recorded steps).
- `POST weight-production/{id}/finish`: release output using `expected_step`.
- `GET finished-stock`: finished weight/value by location and purity.
- `POST finished-opening`: seed explicitly valued finished gold.
- `POST supplier-weight-sales`: sell multiple purity/weight/making-per-gram lines.
- `GET supplier-weight-sales/{sale_id}`: read the saved purity lines.
- `POST weight-internal-invoices`: supply Showroom by purity and weight.
- `GET pending-receipts`: unregistered Showroom weight from factory supplies.
- `POST weight-internal-invoices/{id}/receive`: create Showroom pieces/photos.
- `POST weight-internal-invoices/{id}/photos`: stage a receipt photo for an
  admin in Showroom while that weight invoice still has a pending receipt.

All writes use `Idempotency-Key`. Employees and admins can run production.
Admins handle seeding, supplier sales, internal supply, and Showroom receipts.
Existing production history/detail and specialized reversals
remain available. Earlier piece-creation/sale/supply routes are deprecated
compatibility endpoints; current factory screens use the weight routes.


## Customer ounce-price adjustments

Each workspace has independent **buying** and **selling** USD-per-ounce adjustments,
both defaulting to zero. Admins edit them from **Customer price adjustments** on
the dashboard. Enter a positive amount to add to the active ounce quote or a
negative amount to subtract. The server records the editor and update time.

For customer gold sales, apply the selling adjustment; for walk-in customer bulk
purchases/opening-stock entries, apply the buying adjustment. Given adjustment A:

- Applied ounce = market ounce + A.
- 24K physical gram = applied ounce / 31.1.
- 21K physical gram = (applied ounce / 31.1) × 0.875 / 0.995.
- 18K physical gram = (applied ounce / 31.1) × 0.75 / 0.995.

The recorded rate is rounded once to four decimal places using HALF_UP. Signed
adjustments accept at most two decimal places. A nonpositive adjusted ounce blocks
the affected customer trade before stock or cash is posted. The dashboard still
shows the market quote and any valid customer profile so admins can correct settings.

Customer transactions save `market_ounce_usd`, `ounce_adjustment_usd`,
`applied_ounce_usd`, quote time and the resulting per-line gram rates. Later edits
use the new settings only for new trades. Retry receipts retain the original price
snapshot. Historical records keep their existing prices and have null ounce-snapshot
fields; the migration does not infer or rewrite old rates. Actual customer payment
and final selling totals are entered separately; purchase carrying cost uses actual
payment, and sale revenue uses actual collection.

Supplier purchases/sales and factory/internal price suggestions use the market
quote or their entered agreed rate. Gold-weight conversion and commercial repayment
factors continue to be applied for their respective weight and settlement workflows.

`GET /api/v1/gold-price` retains its raw quote fields and adds `customer_buy`,
`customer_sell` and `price_settings`. Both profiles are derived from the same raw
quote cached across workspaces/workers for 30 seconds; adding profiles or changing
settings does not bypass the upstream cooldown. `GET /api/v1/gold-price/settings`
reads the active workspace's settings, and admin-only `PUT` replaces both signed
adjustments. Configuration can be edited without an available external quote.

Admins can use **Gold quote settings** on Overview to enter a positive manual
USD-per-ounce quote for the current workspace. Trades in that workspace use the
saved quote until the admin switches back to live pricing. Customer buying and
selling adjustments apply to either source. The manual quote remains usable
regardless of its age. The admin-only `PUT /api/v1/gold-price/quote-mode` endpoint
accepts `manual_ounce_usd` or `null` to resume live pricing.

## Default location

Admins set a shared default under **Default location** on Overview. New forms
preselect it in Factory and Showroom. Users can choose a different location on
individual entries. Stock transfers preselect the source. Internal payments
preselect the current workspace's location. Choose the second location when a
form requires one.

## Admin corrections

Admins make corrections from the screen that owns the record. Catalog,
supplier and staff records can be deleted when no other record depends on
them. Staff with linked history can be deactivated. An administrator
can update another staff account's details and role.

Financial and production corrections follow the associated workflow.

- Purchases allow invoice-number and note corrections. A supplier invoice can be
  voided while its original pieces are untouched. A bulk purchase can be voided
  when its saved stock credit still matches the current balance. Voids retain the
  original invoice and reverse its stock and financial effects.
- Cash Drawer allows admins to correct standalone expenses, withdrawals and
  reconciliations. A closed drawer period must be reopened before changing a
  cash amount or removing a cash movement in that period. Servicing corrects a
  payment and its cash entry together.
- Factory / Showroom account invoices and payments allow note changes and
  reversals. Factory production supports edits to references and notes. To
  correct weights or costs, reverse the affected operation and record it again.
  Only the latest step of an in-progress batch can be reversed individually.

Run `uv run alembic upgrade head` before using this version. The purchase and
reconciliation migrations add correction fields to existing records. Downgrade
requires restoring a reviewed backup if purchases or reconciliations have
already been voided.
