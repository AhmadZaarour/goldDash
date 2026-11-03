from fastapi import APIRouter, Response

from app.core.dependencies import CurrentUser
from app.services.gold_price import get_quote

router = APIRouter(prefix="/gold-price", tags=["Gold price"])


@router.get("")
async def current_price(user: CurrentUser, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return await get_quote()
