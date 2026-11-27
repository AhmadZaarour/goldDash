from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import AdminUser
from app.core.database import get_db
from app.core.dependencies import CurrentUser
from app.schemas.gold_price import PriceSettingsResponse, PriceSettingsUpdate, QuoteModeUpdate
from app.services.customer_pricing import (
    price_settings,
    quote_profiles,
    save_quote_mode,
    save_settings,
)
from app.services.gold_price import effective_quote, get_quote

router = APIRouter(prefix="/gold-price", tags=["Gold price"])
Database = Annotated[AsyncSession, Depends(get_db)]


@router.get("")
async def current_price(user: CurrentUser, response: Response, db: Database):
    response.headers["Cache-Control"] = "no-store"
    return await quote_profiles(db, await effective_quote(db, get_quote))


@router.get("/settings", response_model=PriceSettingsResponse)
async def current_settings(user: CurrentUser, response: Response, db: Database):
    response.headers["Cache-Control"] = "no-store"
    return await price_settings(db)


@router.put("/settings", response_model=PriceSettingsResponse)
async def update_settings(data: PriceSettingsUpdate, user: AdminUser, db: Database):
    return await save_settings(db, data, user.id)


@router.put("/quote-mode", response_model=PriceSettingsResponse)
async def update_quote_mode(data: QuoteModeUpdate, user: AdminUser, db: Database):
    return await save_quote_mode(db, data, user.id)
