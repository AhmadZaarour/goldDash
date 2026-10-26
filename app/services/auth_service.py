from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.models.user import User, UserRole
from app.schemas.auth import TokenResponse
from app.schemas.user import UserCreate


async def create_user(
    db: AsyncSession,
    user_data: UserCreate,
) -> User:

    existing_user = await db.scalar(
        select(User).where(
            User.email == user_data.email,
        )
    )

    if existing_user is not None:
        raise ValueError("User already exists")

    if user_data.role not in UserRole:
        raise ValueError("Invalid role")

    if user_data.role == UserRole.ADMIN:
        raise ValueError("Cannot create admin user")

    user = User(
        email=user_data.email,
        username=user_data.username,
        password_hash=hash_password(user_data.password),
        role=user_data.role,
    )

    db.add(user)

    await db.commit()
    await db.refresh(user)

    return user


async def authenticate_user(
    db: AsyncSession,
    email: str,
    password: str,
) -> User | None:

    user = await db.scalar(
        select(User).where(
            User.email == email,
        )
    )

    if user is None:
        return None

    if not verify_password(
        password,
        user.password_hash,
    ):
        return None

    return user


def create_access_token_for_user(
    user: User,
) -> str:
    return create_access_token(
        str(user.id),
    )