import pytest
from httpx import AsyncClient

from app.core.security import hash_password
from app.models.location import Location
from app.models.purchase import Purchase
from app.models.sales import Sale
from app.models.user import User

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest.mark.parametrize(
    ("resource", "model", "foreign_key", "gold", "making"),
    [
        ("purchaseBook", Purchase, "purchase_id", "paid_gold_charge", "paid_making_charge"),
        ("saleBook", Sale, "sale_id", "recieved_gold_charge", "recieved_making_charge"),
    ],
)
async def test_book_lifecycle(
    client: AsyncClient, test_session_factory, resource, model, foreign_key, gold, making
):
    async with test_session_factory() as db:
        user = User(
            email="book@example.com",
            username="book-user",
            password_hash=hash_password("BookTestPassword123!"),
            role="employee",
        )
        location = Location(name="Shop", code="SHOP", address="Main street")
        db.add_all([user, location])
        await db.flush()
        transaction = model(invoice_number="INV-1", created_by=user.id, location_id=location.id)
        db.add(transaction)
        await db.commit()
        await db.refresh(transaction)
        transaction_id = transaction.id
    url = f"/api/v1/{resource}"
    assert (await client.get(url)).json() == []
    payload = {foreign_key: transaction_id, gold: 10.5, making: 2.5}
    created = await client.post(url, json=payload)
    assert created.status_code == 201, created.text
    record = created.json()
    assert all(record[k] == v for k, v in payload.items())
    detail = f"{url}/{record['id']}"
    assert (await client.get(detail)).json() == record
    assert (await client.post(url, json=payload)).status_code == 409
    updated = await client.patch(detail, json={gold: 20.5})
    assert updated.status_code == 200, updated.text
    assert updated.json()[gold] == 20.5
    assert updated.json()[making] == 2.5
    assert updated.json()[foreign_key] == transaction_id
    assert (await client.get(detail)).json() == updated.json()
    assert (await client.get(url)).json() == [updated.json()]
    assert (await client.get(f"{url}/2147483647")).status_code == 404
    assert (await client.patch(f"{url}/2147483647", json={gold: 1})).status_code == 404
