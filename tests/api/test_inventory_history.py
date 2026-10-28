from datetime import timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import event

from app.models import (
    Category,
    GoldPurity,
    InventoryBalance,
    InventoryItem,
    InventoryMovement,
    ItemReturn,
    Location,
    Product,
    Purchase,
    PurchaseItem,
    Sale,
    SaleItem,
    StockTransferRecord,
    Supplier,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest_asyncio.fixture(loop_scope="session")
async def history_data(client, test_session_factory):
    actor_id = (await client.get("/api/v1/auth/me")).json()["id"]
    async with test_session_factory() as db:
        first = Location(name="First shop", code="FIRST", address="First street")
        second = Location(name="Second shop", code="SECOND", address="Second street")
        category = Category(name="Rings")
        purity = GoldPurity(name="24K", karat=24, purity=99.9)
        other_purity = GoldPurity(name="22K", karat=22, purity=91.6)
        supplier = Supplier(name="History supplier", phone="123")
        db.add_all([first, second, category, purity, other_purity, supplier])
        await db.flush()
        product = Product(
            sku="HISTORY",
            name="Ring",
            category_id=category.id,
            purity_id=purity.id,
            inventory_type="item",
        )
        purchase = Purchase(
            created_by=actor_id,
            location_id=first.id,
            supplier_id=supplier.id,
        )
        original_sale = Sale(created_by=actor_id, location_id=first.id)
        resale = Sale(created_by=actor_id, location_id=second.id)
        db.add_all([product, purchase, original_sale, resale])
        await db.flush()
        purchase_line = PurchaseItem(
            supplier_id=supplier.id,
            purchase_id=purchase.id,
            product_id=product.id,
            weight=1,
            gold_price_per_gram=45,
            gold_charge_in_grams=1,
            making_charge=5,
        )
        db.add(purchase_line)
        await db.flush()
        item = InventoryItem(
            purchase_item_id=purchase_line.id,
            location_id=second.id,
            barcode="HISTORY-ITEM",
            status="sold",
        )
        db.add(item)
        await db.flush()
        old_line = SaleItem(
            sale_id=original_sale.id,
            inventory_item_id=item.id,
            gold_price_per_gram=45,
            discount=0,
            sell_price=50,
        )
        current_line = SaleItem(
            sale_id=resale.id,
            inventory_item_id=item.id,
            gold_price_per_gram=45,
            discount=0,
            sell_price=55,
        )
        db.add_all([old_line, current_line])
        await db.flush()
        returned = ItemReturn(
            sale_item_id=old_line.id,
            location_id=first.id,
            refund_usd=Decimal("30.25"),
            created_by=actor_id,
        )
        purchase_event = InventoryMovement(
            inventory_item_id=item.id,
            movement_type="purchase",
            created_by=actor_id,
            to_location_id=first.id,
        )
        item_transfer = InventoryMovement(
            inventory_item_id=item.id,
            movement_type="transfer",
            created_by=actor_id,
            from_location_id=first.id,
            to_location_id=second.id,
        )
        transfer1 = StockTransferRecord(
            purity_id=purity.id,
            source_location_id=first.id,
            source_placement="factory",
            destination_location_id=second.id,
            destination_placement="showroom",
            weight=Decimal("2.000"),
            created_by=actor_id,
        )
        transfer2 = StockTransferRecord(
            purity_id=other_purity.id,
            source_location_id=second.id,
            source_placement="showroom",
            destination_location_id=first.id,
            destination_placement="factory",
            weight=Decimal("1.000"),
            created_by=actor_id,
        )
        balances = [
            InventoryBalance(
                purity_id=purity.id, location_id=first.id, placement="factory", total_weight=8
            ),
            InventoryBalance(
                purity_id=purity.id, location_id=first.id, placement="showroom", total_weight=2
            ),
            InventoryBalance(
                purity_id=purity.id, location_id=second.id, placement="factory", total_weight=5
            ),
            InventoryBalance(
                purity_id=other_purity.id,
                location_id=second.id,
                placement="showroom",
                total_weight=1,
            ),
        ]
        db.add_all([returned, purchase_event, item_transfer, transfer1, transfer2, *balances])
        await db.commit()
        return {
            "actor": actor_id,
            "first": first.id,
            "second": second.id,
            "purity": purity.id,
            "other_purity": other_purity.id,
            "item": item.id,
            "old_sale": original_sale.id,
            "new_sale": resale.id,
            "old_line": old_line.id,
            "new_line": current_line.id,
            "return": returned.id,
            "returned_at": returned.created_at,
            "purchase_event": purchase_event.id,
            "item_transfer": item_transfer.id,
            "stock_transfer": transfer1.id,
            "other_stock_transfer": transfer2.id,
            "balances": [balance.id for balance in balances],
        }


async def test_return_history_exposes_source_and_refund_details(client, history_data):
    data = history_data
    response = await client.get(
        "/api/v1/inventory/returns",
        params={
            "sale_id": data["old_sale"],
            "inventory_item_id": data["item"],
            "location_id": data["first"],
            "created_by": data["actor"],
            "limit": 1,
        },
    )
    assert response.status_code == 200, response.text
    assert response.headers["X-Total-Count"] == "1"
    record = response.json()[0]
    assert record["id"] == data["return"]
    assert record["sale_item_id"] == data["old_line"]
    assert record["inventory_item_id"] == data["item"]
    assert record["sale_id"] == data["old_sale"]
    assert record["refund_usd"] == "30.25"
    assert (await client.get(f"/api/v1/inventory/returns/{data['return']}")).json() == record
    assert (
        await client.get("/api/v1/inventory/returns", params={"sale_id": data["new_sale"]})
    ).json() == []
    assert (await client.get("/api/v1/inventory/returns", params={"offset": 1})).json() == []
    assert (await client.get("/api/v1/inventory/returns/2147483647")).status_code == 404


async def test_sale_lines_expose_return_state_even_after_item_is_resold(
    client, history_data, test_engine
):
    data = history_data
    statements = []

    def track(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT") and 'FROM "saleItems"' in statement:
            statements.append(statement)

    event.listen(test_engine.sync_engine, "before_cursor_execute", track)
    try:
        original = await client.get(f"/api/v1/sales/item/{data['old_sale']}")
    finally:
        event.remove(test_engine.sync_engine, "before_cursor_execute", track)
    assert original.status_code == 200
    assert len(statements) == 1
    record = original.json()[0]
    assert record["returned"] is True
    assert record["return_id"] == data["return"]
    assert record["refund_usd"] == "30.25"
    assert record["returned_at"]
    resale = (await client.get(f"/api/v1/sales/item/{data['new_sale']}")).json()[0]
    assert resale["returned"] is False
    assert resale["return_id"] is None
    assert resale["refund_usd"] == "0"
    assert resale["returned_at"] is None


async def test_item_transfer_history_excludes_other_movements(client, history_data):
    data = history_data
    response = await client.get(
        "/api/v1/inventory/transfers/items",
        params={
            "inventory_item_id": data["item"],
            "location_id": data["second"],
            "from_location_id": data["first"],
            "to_location_id": data["second"],
            "created_by": data["actor"],
        },
    )
    assert response.status_code == 200, response.text
    assert response.headers["X-Total-Count"] == "1"
    record = response.json()[0]
    assert record["id"] == data["item_transfer"]
    assert record["movement_type"] == "transfer"
    assert (await client.get(f"/api/v1/inventory/transfers/items/{record['id']}")).json() == record
    assert (
        await client.get(f"/api/v1/inventory/transfers/items/{data['purchase_event']}")
    ).status_code == 404


async def test_bulk_transfer_history_filters_and_paginates(client, history_data):
    data = history_data
    response = await client.get("/api/v1/inventory/transfers/stocks", params={"limit": 1})
    assert response.status_code == 200, response.text
    assert response.headers["X-Total-Count"] == "2"
    assert response.json()[0]["id"] == data["stock_transfer"]
    assert response.json()[0]["weight"] == "2.000"
    second = await client.get(
        "/api/v1/inventory/transfers/stocks", params={"limit": 1, "offset": 1}
    )
    assert second.json()[0]["id"] == data["other_stock_transfer"]
    filtered = await client.get(
        "/api/v1/inventory/transfers/stocks",
        params={
            "purity_id": data["purity"],
            "source_location_id": data["first"],
            "destination_location_id": data["second"],
            "source_placement": "factory",
            "destination_placement": "showroom",
            "location_id": data["second"],
            "created_by": data["actor"],
        },
    )
    assert filtered.headers["X-Total-Count"] == "1"
    record = filtered.json()[0]
    assert (await client.get(f"/api/v1/inventory/transfers/stocks/{record['id']}")).json() == record
    assert (await client.get("/api/v1/inventory/transfers/stocks/2147483647")).status_code == 404


async def test_balance_filters_and_pagination(client, history_data):
    data = history_data
    response = await client.get("/api/v1/balance", params={"limit": 1, "offset": 1})
    assert response.status_code == 200
    assert response.headers["X-Total-Count"] == "4"
    assert response.json()[0]["id"] == data["balances"][1]
    filtered = await client.get(
        "/api/v1/balance",
        params={
            "location_id": data["first"],
            "purity_id": data["purity"],
            "placement": "factory",
        },
    )
    assert filtered.headers["X-Total-Count"] == "1"
    assert filtered.json()[0]["id"] == data["balances"][0]
    assert filtered.json()[0]["total_weight"] == "8.000"
    assert (await client.get("/api/v1/balance", params={"placement": "invalid"})).status_code == 422
    assert (await client.get("/api/v1/balance", params={"limit": 101})).status_code == 422


@pytest.mark.parametrize(
    "path", ["/inventory/returns", "/inventory/transfers/items", "/inventory/transfers/stocks"]
)
async def test_history_authentication_and_period_validation(client, history_data, path):
    assert (await client.get(f"/api/v1{path}", headers={"Authorization": ""})).status_code == 401
    returned_at = history_data["returned_at"]
    valid = await client.get(
        f"/api/v1{path}",
        params={
            "from_at": (returned_at - timedelta(days=1)).isoformat(),
            "to_at": (returned_at + timedelta(days=1)).isoformat(),
        },
    )
    assert valid.status_code == 200
    reversed_period = await client.get(
        f"/api/v1{path}",
        params={
            "from_at": (returned_at + timedelta(days=1)).isoformat(),
            "to_at": returned_at.isoformat(),
        },
    )
    assert reversed_period.status_code == 422
    assert (await client.get(f"/api/v1{path}", params={"limit": 101})).status_code == 422
