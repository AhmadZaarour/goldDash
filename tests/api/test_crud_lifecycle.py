"""Exercise persistence, uniqueness conflicts, and missing-resource responses."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio(loop_scope="session")

RESOURCES = [
    ("categories", {"name": "Rings", "description": "Gold rings"}, {"description": "Updated"}),
    (
        "locations",
        {"name": "Shop", "code": "S1", "address": "Main street"},
        {"address": "New street"},
    ),
    (
        "goldpurities",
        {"name": "Fine", "karat": 24, "purity": 99.9},
        {"name": "Fine", "karat": 22, "purity": 91.6},
    ),
    ("suppliers", {"name": "Supplier", "phone": "123"}, {"phone": "456", "is_active": False}),
    ("customers", {"name": "Customer", "phone": "123"}, {"name": "Customer", "phone": "456"}),
]


@pytest.mark.parametrize(("resource", "payload", "update"), RESOURCES)
async def test_resource_lifecycle(client: AsyncClient, resource, payload, update):
    url = f"/api/v1/{resource}"
    created = await client.post(url, json=payload)
    assert created.status_code == 201, created.text
    record = created.json()
    assert all(record[key] == value for key, value in payload.items())
    detail_url = f"{url}/{record['id']}"
    fetched = await client.get(detail_url)
    assert fetched.status_code == 200
    assert fetched.json() == record

    duplicate = await client.post(url, json=payload)
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]

    patched = await client.patch(detail_url, json=update)
    assert patched.status_code == 200, patched.text
    assert all(patched.json()[key] == value for key, value in update.items())
    persisted = await client.get(detail_url)
    assert persisted.json() == patched.json()

    other_payload = {**payload, "name": "Other"}
    if resource == "locations":
        other_payload["code"] = "S2"
    other = await client.post(url, json=other_payload)
    assert other.status_code == 201
    conflict = await client.patch(detail_url, json={**update, "name": "Other"})
    assert conflict.status_code == 409
    assert (await client.get(detail_url)).json() == patched.json()

    missing = f"{url}/2147483647"
    assert (await client.get(missing)).status_code == 404
    assert (await client.patch(missing, json=update)).status_code == 404

    if resource in {"customers", "suppliers"}:
        listed = await client.get(url)
        assert listed.status_code == 200
        assert [row["id"] for row in listed.json()] == [record["id"], other.json()["id"]]
