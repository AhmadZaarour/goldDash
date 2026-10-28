"""Database-backed regression tests for inventory identities and transaction races."""

import asyncio
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.security import hash_password
from app.models import (
    Category,
    GoldPurity,
    InventoryBalance,
    InventoryItem,
    InventoryMovement,
    Location,
    Product,
    Purchase,
    PurchaseItem,
    Sale,
    SaleItem,
    Supplier,
    User,
)
from app.schemas.sales import SaleCreate, SaleStockCreate
from app.services.sale_service import create_item_sale, create_stock_sale

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest_asyncio.fixture(loop_scope="session")
async def inventory(test_session_factory):
    async with test_session_factory() as db:
        user = User(
            email="inventory@example.com",
            username="inventory",
            role="employee",
            password_hash=hash_password("InventoryTest123!"),
        )
        location = Location(name="Shop", code="SHOP", address="Main street")
        supplier = Supplier(name="Supplier", phone="123")
        category = Category(name="Rings")
        purity = GoldPurity(name="Fine", karat=24, purity=99.9)
        db.add_all([user, location, supplier, category, purity])
        await db.flush()
        product = Product(
            sku="RING",
            name="Ring",
            category_id=category.id,
            purity_id=purity.id,
            inventory_type="item",
        )
        db.add(product)
        await db.flush()
        purchase = Purchase(created_by=user.id, location_id=location.id, supplier_id=supplier.id)
        db.add(purchase)
        await db.flush()
        line = PurchaseItem(
            id=10001,
            purchase_id=purchase.id,
            supplier_id=supplier.id,
            product_id=product.id,
            weight=2,
            gold_price_per_gram=100,
            gold_charge_in_grams=2,
            making_charge=5,
        )
        db.add(line)
        await db.flush()
        item = InventoryItem(
            id=20001,
            purchase_item_id=line.id,
            location_id=location.id,
            barcode="BARCODE",
            status="in_stock",
        )
        balance = InventoryBalance(
            purity_id=purity.id,
            location_id=location.id,
            placement="factory",
            total_weight=Decimal("10.000"),
        )
        db.add_all([item, balance])
        await db.flush()
        db.add(InventoryMovement(inventory_item_id=item.id, movement_type="purchase"))
        await db.commit()
        return dict(
            user_id=user.id,
            location_id=location.id,
            supplier_id=supplier.id,
            purity_id=purity.id,
            item_id=item.id,
            line_id=line.id,
            balance_id=balance.id,
        )


def item_sale(data, **overrides):
    return SaleCreate(
        created_by=data["user_id"],
        location_id=data["location_id"],
        items=[
            {
                "inventory_item_id": data["item_id"],
                "gold_price_per_gram": 100,
                "discount": 0,
                "sell_price": 205,
                **overrides,
            }
        ],
    )


def stock_sale(data, weight):
    return SaleStockCreate(
        created_by=data["user_id"],
        location_id=data["location_id"],
        item={
            "supplier_id": data["supplier_id"],
            "gold_purity_id": data["purity_id"],
            "weight": weight,
            "gold_charge_in_grams": weight,
            "making_charge": 1,
        },
    )


async def test_item_identity_and_append_only_history(client, test_session_factory, inventory):
    detail = await client.get(f"/api/v1/inventory/items/{inventory['item_id']}")
    assert detail.status_code == 200
    assert detail.json()["purchase_item_id"] == inventory["line_id"]
    assert (await client.get(f"/api/v1/inventory/items/{inventory['line_id']}")).status_code == 404
    async with test_session_factory() as db:
        await create_item_sale(db, item_sale(inventory))
    async with test_session_factory() as db:
        item = await db.get(InventoryItem, inventory["item_id"])
        assert item.status == "sold"
        movements = list(
            await db.scalars(
                select(InventoryMovement)
                .where(InventoryMovement.inventory_item_id == item.id)
                .order_by(InventoryMovement.id)
            )
        )
        assert [m.movement_type for m in movements] == ["purchase", "sale"]
    for path in ("items", "stocks", "movements"):
        assert (await client.get(f"/api/v1/inventory/{path}")).status_code == 200
    response = await client.get(f"/api/v1/inventory/movements/{movements[-1].id}")
    assert response.status_code == 200
    assert response.json()["movement_type"] == "sale"


async def test_concurrent_item_sales_allow_one_winner(test_session_factory, inventory):
    async def sell():
        async with test_session_factory() as db:
            try:
                await create_item_sale(db, item_sale(inventory))
                return "sold"
            except ValueError as error:
                assert "not available" in str(error)
                return "rejected"

    assert sorted(await asyncio.gather(sell(), sell())) == ["rejected", "sold"]
    async with test_session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(SaleItem)) == 1
        assert await db.scalar(select(func.count()).select_from(Sale)) == 1


async def test_concurrent_bulk_sales_cannot_oversell(test_session_factory, inventory):
    async def sell():
        async with test_session_factory() as db:
            try:
                await create_stock_sale(db, stock_sale(inventory, 7))
                return "sold"
            except ValueError as error:
                assert "Insufficient" in str(error)
                return "rejected"

    assert sorted(await asyncio.gather(sell(), sell())) == ["rejected", "sold"]
    async with test_session_factory() as db:
        balance = await db.get(InventoryBalance, inventory["balance_id"])
        assert balance.total_weight == Decimal("3.000")
        assert await db.scalar(select(func.count()).select_from(Sale)) == 1


async def test_failed_sale_rolls_back_all_lines(test_session_factory, inventory):
    payload = item_sale(inventory)
    payload.items.append(payload.items[0].model_copy(update={"inventory_item_id": 2147483647}))
    async with test_session_factory() as db:
        with pytest.raises(ValueError, match="does not exist"):
            await create_item_sale(db, payload)
    async with test_session_factory() as db:
        assert (await db.get(InventoryItem, inventory["item_id"])).status == "in_stock"
        assert await db.scalar(select(func.count()).select_from(Sale)) == 0
        assert await db.scalar(select(func.count()).select_from(InventoryMovement)) == 1


@pytest.mark.parametrize("case", ["negative", "duplicate", "placement"])
async def test_balance_constraints(test_session_factory, inventory, case):
    async with test_session_factory() as db:
        if case == "negative":
            balance = await db.get(InventoryBalance, inventory["balance_id"])
            balance.total_weight = -1
        else:
            db.add(
                InventoryBalance(
                    purity_id=inventory["purity_id"],
                    location_id=inventory["location_id"],
                    placement="factory" if case == "duplicate" else "invalid",
                    total_weight=0,
                )
            )
        with pytest.raises(IntegrityError):
            await db.flush()
        await db.rollback()


async def test_negative_bulk_weight_rejected(client, inventory):
    from tests.api.test_auth import login_user

    tokens = await login_user(client)
    payload = stock_sale(inventory, 1).model_dump(mode="json")
    payload["item"]["weight"] = -1
    assert (
        await client.post(
            "/api/v1/sales/stock",
            json=payload,
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
    ).status_code == 422


async def test_return_resale_and_transfer_preserve_history(client, test_session_factory, inventory):
    from tests.api.test_auth import login_user

    tokens = await login_user(client)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    async with test_session_factory() as db:
        await create_item_sale(db, item_sale(inventory))
        line = await db.scalar(select(SaleItem))
        line_id = line.id
        location = Location(name="Branch", code="BRANCH", address="Branch street")
        db.add(location)
        await db.commit()
        branch_id = location.id
    payload = {
        "sale_item_id": line_id,
        "location_id": inventory["location_id"],
        "refund_usd": "205.00",
    }
    returned = await client.post("/api/v1/inventory/returns", json=payload, headers=headers)
    assert returned.status_code == 201, returned.text
    assert (
        await client.post("/api/v1/inventory/returns", json=payload, headers=headers)
    ).status_code == 409
    transfer = await client.post(
        f"/api/v1/inventory/items/{inventory['item_id']}/transfer",
        json={"location_id": branch_id},
        headers=headers,
    )
    assert transfer.status_code == 200, transfer.text
    async with test_session_factory() as db:
        with pytest.raises(ValueError, match="location"):
            await create_item_sale(db, item_sale(inventory))
    async with test_session_factory() as db:
        payload = item_sale(inventory).model_copy(update={"location_id": branch_id})
        await create_item_sale(db, payload)
        movements = list(
            await db.scalars(
                select(InventoryMovement.movement_type)
                .where(InventoryMovement.inventory_item_id == inventory["item_id"])
                .order_by(InventoryMovement.id)
            )
        )
        assert movements == ["purchase", "sale", "return", "transfer", "sale"]
        assert await db.scalar(select(func.count()).select_from(SaleItem)) == 2


async def test_bulk_transfer_conserves_weight(client, test_session_factory, inventory):
    from tests.api.test_auth import login_user

    tokens = await login_user(client)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    data = {
        "purity_id": inventory["purity_id"],
        "source_location_id": inventory["location_id"],
        "destination_location_id": inventory["location_id"],
        "source_placement": "factory",
        "destination_placement": "showroom",
        "weight": "3.250",
    }
    response = await client.post("/api/v1/inventory/stocks/transfer", json=data, headers=headers)
    assert response.status_code == 200, response.text
    assert Decimal(response.json()["source_weight"]) == Decimal("6.750")
    assert Decimal(response.json()["destination_weight"]) == Decimal("3.250")
    assert (
        await client.post(
            "/api/v1/inventory/stocks/transfer", json={**data, "weight": "100"}, headers=headers
        )
    ).status_code == 409
    async with test_session_factory() as db:
        total = await db.scalar(select(func.sum(InventoryBalance.total_weight)))
        assert total == Decimal("10.000")


async def test_generated_barcodes_retry_collisions_without_losing_purchase(
    test_session_factory, inventory, monkeypatch
):
    from app.schemas.inventory import InventoryItemCreate
    from app.services.inventory_service import create_item

    async with test_session_factory() as db:
        existing = await db.get(InventoryItem, inventory["item_id"])
        existing.barcode = "GI" + "A" * 16
        line = await db.get(PurchaseItem, inventory["line_id"])
        new_line = PurchaseItem(
            purchase_id=line.purchase_id,
            supplier_id=line.supplier_id,
            product_id=line.product_id,
            weight=1,
            gold_price_per_gram=100,
            gold_charge_in_grams=1,
            making_charge=5,
        )
        db.add(new_line)
        await db.flush()
        values = iter(["a" * 16, "b" * 16])
        monkeypatch.setattr(
            "app.services.inventory_service.secrets.token_hex", lambda _: next(values)
        )
        item = await create_item(
            db,
            InventoryItemCreate(
                purchase_item_id=new_line.id,
                location_id=inventory["location_id"],
                status="in_stock",
            ),
        )
        assert item.barcode == "GI" + "B" * 16
        await db.commit()
        assert (await db.get(InventoryItem, existing.id)).barcode == "GI" + "A" * 16
        assert await db.scalar(select(func.count()).select_from(InventoryItem)) == 2
