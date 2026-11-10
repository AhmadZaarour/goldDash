"""Monthly customer-sale margin at the recorded sale gold price."""

from typing import Annotated
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.insights_service import monthly_profit_service
from app.core.authorization import AdminUser
from app.core.database import get_db
from app.schemas.insights import MonthlyProfit

router = APIRouter(prefix="/insights", tags=["Insights"])


@router.get("/monthly-profit", response_model=MonthlyProfit)
async def monthly_profit(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: AdminUser,
    month: str = Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    location_id: int | None = Query(None, gt=0),
):
    return await monthly_profit_service(db, month, location_id)
