from decimal import Decimal

import pytest
from httpx import AsyncClient

from app.core.security import create_access_token, hash_password
from app.models.categories import Category
from app.models.goldPriceSettings import GoldPriceSettings
from app.models.goldPurities import GoldPurity
from app.models.product import Product
from app.models.user import User

pytestmark = pytest.mark.asyncio(loop_scope="session")
PATH = "/api/v1/admin/data"


async def test_admin_data_mutations_are_admin_only(client: AsyncClient):
    async with client.test_session_factory() as db:
        employee = User(
            email="staff@example.com",
            username="staff",
            password_hash=hash_password("FixturePassword123!"),
            role="employee",
        )
        db.add(employee)
        await db.commit()
    headers = {"Authorization": f"Bearer {create_access_token(str(employee.id))}"}
    assert (await client.get(PATH, headers=headers)).status_code == 403
    body = {"key": {"id": 1}, "changes": {"name": "Other"}}
    assert (await client.patch(f"{PATH}/categories", json=body, headers=headers)).status_code == 403
    response = await client.request(
        "DELETE", f"{PATH}/categories", json={"key": {"id": 1}}, headers=headers
    )
    assert response.status_code == 403


async def test_admin_can_correct_across_workspaces_with_exact_numeric_values(client: AsyncClient):
    async with client.test_session_factory() as db:
        db.add(GoldPriceSettings(unit="factory"))
        await db.commit()

    headers = {"X-Business-Unit": "legacy"}
    url = f"{PATH}/gold_price_settings"
    listing = await client.get(url, headers=headers)
    assert listing.json()["items"][0]["key"] == {"unit": "factory"}
    assert (await client.get(url, params={"key": "showroom"})).json()["total"] == 0
    assert (await client.get(url, params={"key": "factory"})).json()["total"] == 1

    body = {"key": {"unit": "factory"}, "changes": {"sell_adjustment_usd": "12.34"}}
    updated = await client.patch(url, json=body, headers=headers)
    assert updated.status_code == 200
    assert updated.json()["values"]["sell_adjustment_usd"] == "12.34"
    body["changes"]["sell_adjustment_usd"] = "1.234"
    assert (await client.patch(url, json=body)).status_code == 422
    assert (await client.get(url)).json()["items"][0]["values"]["sell_adjustment_usd"] == "12.34"

    result = await client.request("DELETE", url, json={"key": body["key"]}, headers=headers)
    assert result.status_code == 204
    assert (await client.get(url)).json() == {"items": [], "total": 0}


async def test_admin_data_preserves_references_and_protects_credentials(client: AsyncClient):
    async with client.test_session_factory() as db:
        category = Category(name="Rings")
        purity = GoldPurity(name="18k", karat=18, purity=Decimal("75"))
        db.add_all([category, purity])
        await db.flush()
        db.add(
            Product(
                sku="R-01",
                name="Ring",
                category_id=category.id,
                purity_id=purity.id,
                inventory_type="item",
            )
        )
        await db.commit()

    response = await client.request(
        "DELETE", f"{PATH}/categories", json={"key": {"id": category.id}}
    )
    assert response.status_code == 409
    assert (await client.get(f"{PATH}/categories")).json()["total"] == 1

    users = (await client.get(f"{PATH}/users")).json()["items"]
    assert all("password_hash" not in row["values"] for row in users)
    admin_key = users[0]["key"]
    for changes in ({"password_hash": "bad"}, {"id": 999}):
        response = await client.patch(f"{PATH}/users", json={"key": admin_key, "changes": changes})
        assert response.status_code == 422
    assert (
        await client.patch(
            f"{PATH}/users", json={"key": admin_key, "changes": {"is_active": False}}
        )
    ).status_code == 409
    assert (
        await client.request("DELETE", f"{PATH}/users", json={"key": admin_key})
    ).status_code == 409
