import pytest

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest.mark.parametrize("resource", ["purchaseBook", "saleBook"])
async def test_legacy_books_are_retired(client, resource):
    for method, path in [("GET", ""), ("POST", ""), ("GET", "/1"), ("PATCH", "/1")]:
        response = await client.request(method, f"/api/v1/{resource}{path}")
        assert response.status_code == 410
        assert "retired" in response.json()["detail"]
