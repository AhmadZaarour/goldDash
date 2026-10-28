from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_role
from app.core.pagination import paginate
from app.models.goldPurities import GoldPurity
from app.models.user import UserRole
from app.schemas.goldPurities import GoldPurityCreate, GoldPurityResponse, GoldPurityUpdate
from app.services.goldPurities_service import (
    create_gold_purity,
    get_gold_purity,
    update_gold_purity,
)

router = APIRouter(
    prefix="/goldpurities",
    tags=["GoldPurities"],
)


@router.post(
    "",
    dependencies=[Depends(require_role(UserRole.ADMIN))],
    response_model=GoldPurityResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_gold_purity_endpoint(
    gold_purities_data: GoldPurityCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GoldPurityResponse:

    try:
        gold_purity = await create_gold_purity(
            db,
            gold_purities_data,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return gold_purity


@router.get(
    "/{goldPurity_id}",
    response_model=GoldPurityResponse,
)
async def get_gold_purity_endpoint(
    goldPurity_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GoldPurityResponse:

    gold_purity = await get_gold_purity(
        db,
        goldPurity_id,
    )

    if gold_purity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Gold purity not found",
        )

    return gold_purity


@router.patch(
    "/{goldPurity_id}",
    dependencies=[Depends(require_role(UserRole.ADMIN))],
    response_model=GoldPurityResponse,
)
async def update_gold_purity_endpoint(
    goldPurity_id: int,
    gold_purity_data: GoldPurityUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GoldPurityResponse:

    gold_purity = await get_gold_purity(
        db,
        goldPurity_id,
    )

    if gold_purity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Gold purity not found",
        )
    try:
        new_gold_purity = await update_gold_purity(
            db,
            gold_purity,
            gold_purity_data,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return new_gold_purity


@router.get("", response_model=list[GoldPurityResponse])
async def list_records(
    db: Annotated[AsyncSession, Depends(get_db)],
    response: Response,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    q: str | None = Query(default=None, min_length=1, max_length=100),
) -> list[GoldPurityResponse]:
    statement = select(GoldPurity).order_by(GoldPurity.id)
    if q:
        statement = statement.where(GoldPurity.name.icontains(q, autoescape=True))
    return await paginate(db, statement, response, limit, offset)
