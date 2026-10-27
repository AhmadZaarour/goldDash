import pytest

from tests.api.test_auth import login_user

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_servicing_create_read_update(client):
    tokens = await login_user(client)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    customer = await client.post(
        "/api/v1/customers", json={"name": "Service customer", "phone": "123"}
    )
    assert customer.status_code == 201
    payload = {"customer_id": customer.json()["id"], "barcode": "REPAIR-1", "cost": "12.50"}
    assert (await client.post("/api/v1/servicing", json=payload)).status_code == 401
    response = await client.post("/api/v1/servicing", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    record = response.json()
    assert record["notes"] is None
    assert record["status"] == "received"
    assert (await client.get("/api/v1/servicing/REPAIR-1", headers=headers)).json() == record
    assert (
        await client.post("/api/v1/servicing", json=payload, headers=headers)
    ).status_code == 409
    updated = await client.patch(
        f"/api/v1/servicing/{record['id']}",
        json={"status": "completed", "cost": "15.25"},
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["status"] == "completed"
    assert (
        await client.get("/api/v1/servicing/REPAIR-1", headers=headers)
    ).json() == updated.json()
    assert (await client.get("/api/v1/servicing", headers=headers)).json() == [updated.json()]
