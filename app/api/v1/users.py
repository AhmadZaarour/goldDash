from fastapi import APIRouter

from app.core.dependencies import CurrentUser
from app.schemas.user import UserResponse


router = APIRouter(
    prefix="/users",
    tags=["Users"],
)


@router.get(
    "/me",
    response_model=UserResponse,
)
async def get_current_user(
    current_user: CurrentUser,
) -> UserResponse:
    return current_user