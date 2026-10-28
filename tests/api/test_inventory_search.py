import pytest

from tests.api.test_purchase import test_create_purchase as create_purchase

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_inventory_search_filters_and_pagination(client, test_session_factory):
    purchase1, _, first = await create_purchase(client, test_session_factory)
    purchase2, _, second = await create_purchase(client, test_session_factory)
    response = await client.get("/api/v1/inventory/items", params={"limit": 1, "sort": "-id"})
    assert response.status_code == 200
    assert response.headers["X-Total-Count"] == "2"
    assert response.json()[0]["id"] == second.json()["id"]
    response = await client.get("/api/v1/inventory/items", params={"limit": 1, "offset": 1})
    assert response.json()[0]["id"] == second.json()["id"]
    for params in [
        {"barcode": first.json()["barcode"]},
        {"q": first.json()["barcode"]},
        {"location_id": purchase1.json()["location_id"]},
        {"purchase_id": purchase1.json()["id"]},
    ]:
        response = await client.get("/api/v1/inventory/items", params=params)
        assert response.headers["X-Total-Count"] == "1"
        assert response.json()[0]["id"] == first.json()["id"]
    assert (await client.get("/api/v1/inventory/items", params={"status": "sold"})).json() == []
    assert (await client.get("/api/v1/inventory/items", params={"q": "%"})).json() == []
    for params in [{"limit": 101}, {"offset": -1}, {"sort": "invalid"}, {"status": "invalid"}]:
        assert (await client.get("/api/v1/inventory/items", params=params)).status_code == 422


@pytest.mark.parametrize(
    "path", ["categories", "goldpurities", "locations", "suppliers", "customers", "products"]
)
async def test_catalog_lists_are_bounded(client, path):
    response = await client.get(f"/api/v1/{path}", params={"limit": 1, "q": "absent"})
    assert response.status_code == 200, response.text
    assert response.headers["X-Total-Count"] == "0"
    assert response.json() == []
    assert (await client.get(f"/api/v1/{path}", params={"limit": 0})).status_code == 422
