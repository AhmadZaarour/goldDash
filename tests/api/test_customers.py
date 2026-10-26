from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.schemas.auth import TokenResponse

from tests.api.test_auth import (
    login_user,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")

