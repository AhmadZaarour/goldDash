from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.schemas.auth import TokenResponse

from tests.api.test_auth import (
    login_user,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")

def gold_purity_payload() -> dict[str, str]:
    suffix = uuid4().hex
    return {
        "name": f"gold-purity-{suffix}",
        "karat": 24,
        "purity": 99.9,
    }

async def test_create_gold_purity(client: AsyncClient):

    login_response = await login_user(client)
    access_token = login_response["access_token"]

    gold_purity_payload_data = gold_purity_payload()

    response_gold_purity = await client.post(
        "/api/v1/goldpurities",
        json=gold_purity_payload_data,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response_gold_purity.status_code == 201
    data = response_gold_purity.json()
    assert data["name"] == gold_purity_payload_data["name"]
    assert data["karat"] == gold_purity_payload_data["karat"]
    assert data["purity"] == gold_purity_payload_data["purity"]
    return response_gold_purity