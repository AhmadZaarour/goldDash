"""Derive customer rates from one shared cached quote, and freeze applied settings."""

from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException
from sqlalchemy.dialects.postgresql import insert

from app.core.workspace import active_unit
from app.models.goldPriceSettings import GoldPriceSettings
from app.schemas.gold_price import PriceSettingsResponse


async def price_settings(db):
    unit = active_unit()
    row = await db.get(GoldPriceSettings, unit, populate_existing=True)
    if row is not None:
        return PriceSettingsResponse.model_validate(row)
    return PriceSettingsResponse(unit=unit, buy_adjustment_usd=0, sell_adjustment_usd=0)


async def save_settings(db, data, user_id):
    unit = active_unit()
    if unit not in {"factory", "showroom"}:
        raise HTTPException(409, "Choose Factory or Showroom to edit customer price adjustments")
    values = {**data.model_dump(), "updated_by": user_id, "updated_at": datetime.now(UTC)}
    statement = insert(GoldPriceSettings).values(unit=unit, **values)
    await db.execute(
        statement.on_conflict_do_update(index_elements=[GoldPriceSettings.unit], set_=values)
    )
    await db.commit()
    return await price_settings(db)


def adjusted_quote(quote, adjustment):
    market = (
        Decimal(str(quote["ounce_usd"]))
        if "ounce_usd" in quote
        else Decimal(quote["gram_24k_usd"]) * Decimal("31.1")
    )
    market = market.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    applied = market + Decimal(adjustment)
    if not applied.is_finite() or applied <= 0:
        raise HTTPException(
            422,
            "Customer ounce adjustment produces a nonpositive gold price; "
            "update the workspace price settings",
        )
    gram = applied / Decimal("31.1")
    return {
        **quote,
        "market_ounce_usd": str(market),
        "ounce_adjustment_usd": str(adjustment),
        "ounce_usd": str(applied),
        "applied_ounce_usd": str(applied),
        "gram_24k_usd": str(gram),
        "gram_21k_usd": str(gram * Decimal("0.875") / Decimal("0.995")),
        "gram_18k_usd": str(gram * Decimal("0.75") / Decimal("0.995")),
    }


async def trade_quote(db, raw_quote, direction):
    settings = await price_settings(db)
    adjustment = settings.buy_adjustment_usd if direction == "buy" else settings.sell_adjustment_usd
    return adjusted_quote(raw_quote, adjustment)


def snapshot(quote):
    return {
        key: Decimal(quote[key])
        for key in ("market_ounce_usd", "ounce_adjustment_usd", "applied_ounce_usd")
    }


async def quote_profiles(db, raw_quote):
    settings = await price_settings(db)
    result = {**raw_quote, "price_settings": settings.model_dump(mode="json")}
    for name, value in [
        ("customer_buy", settings.buy_adjustment_usd),
        ("customer_sell", settings.sell_adjustment_usd),
    ]:
        try:
            result[name] = {**adjusted_quote(raw_quote, value), "available": True}
        except HTTPException as error:
            result[name] = {
                "available": False,
                "error": error.detail,
                "ounce_adjustment_usd": str(value),
            }
    return result
