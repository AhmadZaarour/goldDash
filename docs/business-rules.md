# Inventory and supplier accounting

Supplier purchases and bulk sales settle in gold grams at the transaction's
purity plus USD making charges. Do not convert or net grams across purities.
The supplier ledger is the source of running balances; positive values mean the
shop owes the supplier, negative values mean the supplier owes the shop.
Purchases increase the obligation; bulk sales decrease it. Settlements sent to
the supplier decrease it; settlements received increase it. Customer item sales
do not create supplier receivables or partial-payment plans.

## API changes

- Both purchase creation endpoints require `supplier_id` on the invoice header.
  All item lines must name that same supplier. One item line means one uniquely
  barcoded inventory item. Bulk purchase `item.making_charge` defaults to zero.
- Purchase and sale creation require authentication. The server takes the author
  from the bearer token, regardless of the submitted `created_by` value.
- `GET /api/v1/suppliers/{id}/balance` returns grams grouped by purity ID and a
  separate USD making-charge balance.
- `POST /api/v1/suppliers/{id}/settlements` accepts `idempotency_key`, `direction`
  (`sent` or `received`), `gold_grams`, `purity_id`, and `making_usd`. Gold requires
  a purity; USD-only settlements do not. Repeated keys return 409 rather than
  recording another payment. A settlement records accounting, not an automatic
  physical stock movement: record deliveries through the inventory workflows.
- Inventory reads use `/inventory/items`, `/inventory/stocks`, and
  `/inventory/movements`, with `/{id}` for individual records. The old item-only
  `/inventory` and `/inventory/{id}` routes remain compatibility aliases.
- `POST /inventory/items/{id}/transfer` takes `location_id` and requires the item
  to be in stock. Its movement history records the origin, destination and actor.
- `POST /inventory/returns` takes `sale_item_id`, `location_id`, and `refund_usd`.
  Each sold line can be returned once. Refunds cannot exceed that line's recorded
  `sell_price`. The record acknowledges a cash refund; it does not execute a
  payment. The item becomes available for resale at the return location.
- `POST /inventory/stocks/transfer` takes `purity_id`, source/destination location
  IDs and placements, and a positive `weight`. Transfers conserve total weight.
  All paths above have the `/api/v1` prefix and writes require authentication.
- `/servicing` is now registered and its cost column uses a valid decimal type.

Legacy purchaseBook/saleBook endpoints remain for compatibility. They do not
update the running supplier ledger and should not be used for new supplier
settlements. Their eventual removal needs a separate API migration.

## Integrity and migrations

Stock sales lock available balances and reject negative stock; item sales lock
items, reject duplicates and sold items, and verify the selling location.
Purchases increment unique purity/location/placement buckets atomically.
Movement events append rather than overwrite previous events. Prices, charges,
and weights use fixed-point database storage, with three decimal places for
gold weight and two for USD charges (four for per-gram rates).

The corrective migrations target this disposable development database and the
previous migration-only schema. They are not an automatic repair for an existing
production database built using `create_all` or containing ambiguous supplier
history. Audit and backfill such a database separately before applying them.

Tests now deploy the schema using Alembic. A separate transient-database test
checks upgrade, drift detection, downgrade to base, and replay.

## Follow-up work

Customer identity and a dedicated cash-receipt/reconciliation ledger are not yet
modeled. Item sale prices and return refunds are recorded, but no payment is
executed by these endpoints. Supplier return documents and bulk-sale reversals
need explicit business workflows; do not emulate them with negative quantities.
Legacy invoice-book removal, case-insensitive identity uniqueness, broader role
policies, and production data migration remain separate improvements.

## Item images

Individual purchase lines accept an optional HTTP(S) `image_url` (maximum 2,048
characters). The URL is stored on the barcoded inventory item and returned by
item reads. Existing items default to null. Authenticated clients can set or clear
it with `PATCH /api/v1/inventory/items/{id}/image`, using
`{"image_url": "https://example.com/item.jpg"}` or `{"image_url": null}`.
This stores a URL only; it does not upload or fetch images. Bulk stock has no image field.
