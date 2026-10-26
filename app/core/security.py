from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from pwdlib import PasswordHash
import secrets
from app.core.config import settings


password_hash = PasswordHash.recommended()

algorithm = settings.algorithm

def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(
    password: str,
    hashed_password: str,
) -> bool:
    return password_hash.verify(
        password,
        hashed_password,
    )


def create_access_token(
    subject: str,
) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes,
    )

    payload: dict[str, Any] = {
        "sub": subject,
        "type": "access",
        "exp": expire,
    }

    return jwt.encode(
        payload,
        settings.secret_key,
        algorithm=algorithm,
    )


def create_refresh_token() -> str:
    return secrets.token_urlsafe(64)


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(
        token,
        settings.secret_key,
        algorithms=[algorithm],
    )