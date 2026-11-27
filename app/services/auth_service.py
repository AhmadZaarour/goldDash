from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.models.user import User, UserRole, workspace_for_role
from app.schemas.user import UserCreate

email_address = TypeAdapter(EmailStr)


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
        workspace_access=workspace_for_role(user_data.role),
    )

    db.add(user)

    await db.commit()
    await db.refresh(user)

    return user


async def authenticate_user(
    db: AsyncSession,
    password: str,
    *,
    email: str | None,
    username: str | None,
    identifier: str | None,
) -> User | None:
    query = select(User)
    if identifier is None:
        match = User.email == email if email is not None else User.username == username
        query = query.where(match)
    else:
        username_match = User.username == identifier
        try:
            normalized_email = email_address.validate_python(identifier)
        except ValidationError:
            query = query.where(username_match)
        else:
            email_match = User.email == normalized_email
            # Preserve email sign-in if a username matches another account's email.
            query = query.where(email_match | username_match).order_by(email_match.desc())

    user = await db.scalar(query.limit(1))

    if user is None or not user.is_active:
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
