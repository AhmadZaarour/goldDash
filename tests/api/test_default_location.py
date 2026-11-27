import pytest

from tests.api.test_backend_access import headers_for

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_default_location_is_shared_and_requires_an_active_location(
    client, test_session_factory
):
    path = "/api/v1/locations/default"
    assert (await client.get(path)).json() == {"location_id": None}

    location = await client.post("/api/v1/locations", json={"name": "Main shop", "code": "MAIN"})
    assert location.status_code == 201, location.text
    selected = {"location_id": location.json()["id"]}

    staff = await headers_for(test_session_factory, "cashier")
    denied = await client.put(path, json=selected, headers=staff)
    assert denied.status_code == 403

    response = await client.put(path, json=selected)
    assert response.status_code == 200, response.text
    assert (await client.get(path, headers=staff)).json() == selected
    assert (
        await client.get(path, headers={**staff, "X-Business-Unit": "factory"})
    ).status_code == 403
    employee = await headers_for(test_session_factory, "employee")
    factory = {**employee, "X-Business-Unit": "factory"}
    assert (await client.get(path, headers=factory)).json() == selected

    assert (await client.put(path, json={"location_id": None})).status_code == 200
    assert (await client.get(path, headers=factory)).json() == {"location_id": None}
    assert (await client.put(path, json=selected)).status_code == 200

    deactivated = await client.patch(
        f"/api/v1/locations/{selected['location_id']}", json={"is_active": False}
    )
    assert deactivated.status_code == 200, deactivated.text
    assert (await client.get(path, headers=factory)).json() == {"location_id": None}
    assert (await client.put(path, json=selected)).status_code == 409
