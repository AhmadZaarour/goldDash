from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User
from app.core.database import get_db
from app.core.dependencies import CurrentUser
from app.schemas.auth import (
    LoginRequest,
    RefreshTokenRequest,
    TokenResponse,
)
from app.schemas.user import UserResponse, UserCreate
from app.services.auth_service import (
    create_user,
    authenticate_user,
    create_access_token_for_user,
)
from app.services.session_service import (
    create_refresh_session,
    get_refresh_user_id,
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
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:

    user = await create_user(
        db,
        data,
    )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User already exists",
        )

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

    user_id = await get_refresh_user_id(
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