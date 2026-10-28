from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import AdminUser
from app.core.database import get_db
from app.core.dependencies import CurrentUser
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    RefreshTokenRequest,
    TokenResponse,
)
from app.schemas.user import UserCreate, UserResponse
from app.services.auth_service import (
    authenticate_user,
    create_access_token_for_user,
    create_user,
)
from app.services.session_service import (
    consume_refresh_user_id,
    create_refresh_session,
    revoke_refresh_session,
)

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.post(
    "/register",
    response_model=UserResponse,
)
async def register(
    data: UserCreate,
    admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:

    try:
        user = await create_user(db, data)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error

    return user


@router.post(
    "/login",
    response_model=TokenResponse,
)
async def login(
    data: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:

    user = await authenticate_user(
        db,
        data.email,
        data.password,
    )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={
                "WWW-Authenticate": "Bearer",
            },
        )

    access_token = create_access_token_for_user(
        user,
    )

    refresh_token = await create_refresh_session(
        user.id,
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
)
async def refresh(
    data: RefreshTokenRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:

    user_id = await consume_refresh_user_id(
        data.refresh_token,
    )

    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    user = await db.get(User, user_id)

    if user is None or not user.is_active:
        await revoke_refresh_session(
            data.refresh_token,
        )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    # Rotate refresh token.
    await revoke_refresh_session(
        data.refresh_token,
    )

    new_refresh_token = await create_refresh_session(
        user.id,
    )

    return TokenResponse(
        access_token=create_access_token_for_user(
            user,
        ),
        refresh_token=new_refresh_token,
    )


@router.post("/logout")
async def logout(
    data: RefreshTokenRequest,
) -> dict[str, str]:

    await revoke_refresh_session(
        data.refresh_token,
    )

    return {
        "message": "Successfully logged out",
    }


@router.get(
    "/me",
    response_model=UserResponse,
)
async def get_me(
    current_user: CurrentUser,
) -> UserResponse:

    return current_user
