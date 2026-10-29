import pytest

from tests.api.test_backend_access import headers_for
from tests.api.test_purchase import test_create_purchase as make_purchase

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest.mark.parametrize(
    "grams,rate,making,expected",
    [
        ("2.345", "1.0000", "8.25", "10.60"),
        ("0", "100", "0", "0.00"),
    ],
)
async def test_purchase_base_cost_is_automatic_and_fixed_through_resale(
    client, test_session_factory, grams, rate, making, expected
):
    purchase, lines, _ = await make_purchase(client, test_session_factory)
    data = purchase.json()
    data["supplier_id"] = lines.json()[0]["supplier_id"]
    response = await client.post(
        "/api/v1/purchases/item",
        json={
            "supplier_id": data["supplier_id"],
            "location_id": data["location_id"],
            "items": [
                {
                    "supplier_id": data["supplier_id"],
                    "product_id": lines.json()[0]["product_id"],
                    "weight": "7.777",
                    "gold_charge_in_grams": grams,
                    "gold_price_per_gram": rate,
                    "making_charge": making,
                }
            ],
        },
    )
    assert response.status_code == 201, response.text
    inventory = (
        await client.get("/api/v1/inventory/items", params={"purchase_id": response.json()["id"]})
    ).json()[0]
    assert inventory["weight"] == "7.777"
    assert inventory["base_cost_usd"] == expected
    item_url = f"/api/v1/inventory/items/{inventory['id']}"
    cashier = await headers_for(test_session_factory, "cashier")
    assert (await client.get(item_url, headers=cashier)).json()["base_cost_usd"] == expected
    sale = await client.post(
        "/api/v1/sales/item",
        json={
            "location_id": data["location_id"],
            "items": [
                {
                    "inventory_item_id": inventory["id"],
                    "gold_price_per_gram": "80",
                    "discount": "0",
                    "sell_price": "200",
                }
            ],
        },
    )
    assert sale.status_code == 201
    assert (await client.get(item_url)).json()["base_cost_usd"] == expected
    sale_lines = (await client.get(f"/api/v1/sales/item/{sale.json()['id']}")).json()
    returned = await client.post(
        "/api/v1/inventory/returns",
        json={
            "sale_item_id": sale_lines[0]["id"],
            "location_id": data["location_id"],
            "refund_usd": "150",
        },
    )
    assert returned.status_code == 201
    resale = await client.post(
        "/api/v1/sales/item",
        json={
            "location_id": data["location_id"],
            "items": [
                {
                    "inventory_item_id": inventory["id"],
                    "gold_price_per_gram": "90",
                    "discount": "10",
                    "sell_price": "230",
                }
            ],
        },
    )
    assert resale.status_code == 201
    assert (await client.get(item_url)).json()["base_cost_usd"] == expected
