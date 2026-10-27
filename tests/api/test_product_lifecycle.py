import pytest
from httpx import AsyncClient

from tests.api.test_products import login_admin_user

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_product_persistence_and_sku_conflicts(client: AsyncClient, test_session_factory):
    tokens = await login_admin_user(client, test_session_factory)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    category = await client.post("/api/v1/categories", json={"name": "Rings"})
    purity = await client.post(
        "/api/v1/goldpurities", json={"name": "Fine", "karat": 24, "purity": 99.9}
    )
    payload = {
        "sku": "RING-1",
        "name": "Ring",
        "category_id": category.json()["id"],
        "purity_id": purity.json()["id"],
        "inventory_type": "item",
    }
    url = "/api/v1/products"
    created = await client.post(url, json=payload, headers=headers)
    assert created.status_code == 201
    record = created.json()
    detail = f"{url}/{record['id']}"
    assert (await client.get(detail)).json() == record
    assert (await client.post(url, json=payload, headers=headers)).status_code == 409
    other = await client.post(url, json={**payload, "sku": "RING-2"}, headers=headers)
    assert other.status_code == 201
    updated = await client.patch(
        detail, json={"sku": "RING-3", "name": "New ring"}, headers=headers
    )
    assert updated.status_code == 200
    assert updated.json()["sku"] == "RING-3"
    assert updated.json()["name"] == "New ring"
    assert updated.json()["purity_id"] == payload["purity_id"]
    assert (await client.get(detail)).json() == updated.json()
    conflict = await client.patch(detail, json={"sku": "RING-2"}, headers=headers)
    assert conflict.status_code == 409
    assert (await client.get(detail)).json() == updated.json()
    listed = await client.get(url)
    assert [row["id"] for row in listed.json()] == [record["id"], other.json()["id"]]
    assert (await client.get(f"{url}/2147483647")).status_code == 404
    assert (
        await client.patch(f"{url}/2147483647", json={"name": "Missing"}, headers=headers)
    ).status_code == 404
