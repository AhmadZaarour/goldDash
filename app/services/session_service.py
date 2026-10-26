from app.core.config import settings
from app.core.redis import redis
from app.core.security import create_refresh_token


def _session_key(token: str) -> str:
    return f"auth:refresh:{token}"


async def create_refresh_session(
    user_id: int,
) -> str:
    token = create_refresh_token()

    await redis.set(
        _session_key(token),
        str(user_id),
        ex=settings.refresh_token_expire_days * 24 * 60 * 60,
    )

    return token


async def get_refresh_user_id(
    token: str,
) -> int | None:
    user_id = await redis.get(
        _session_key(token),
    )

    if user_id is None:
        return None

    return int(user_id)


async def revoke_refresh_session(
    token: str,
) -> None:
    await redis.delete(
        _session_key(token),
    )