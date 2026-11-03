"""One shared upstream attempt per 30 seconds, including errors and cache misses."""

import json
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

import httpx
from fastapi import HTTPException
from redis.exceptions import RedisError

from app.core.redis import redis
from app.services.gold_conversion import purchase_factor

QUOTE_KEY = "gold:quote:v1"
COOLDOWN_KEY = "gold:attempt:v1"


async def get_quote():
    try:
        cached = await redis.get(QUOTE_KEY)
        quote = json.loads(cached) if cached else None
        fresh = (
            quote
            and (datetime.now(UTC) - datetime.fromisoformat(quote["fetched_at"])).total_seconds()
            < 30
        )
        if fresh:
            return {**quote, "stale": False}
        # NX also provides a cross-worker lock. Do not delete early: failures must
        # observe the same cooldown. Timeout is shorter than the lock lifetime.
        claimed = await redis.set(COOLDOWN_KEY, "1", nx=True, ex=30)
        if claimed:
            try:
                async with httpx.AsyncClient(timeout=8) as client:
                    response = await client.get("https://api.gold-api.com/price/XAU")
                    response.raise_for_status()
                    data = response.json()
                ounce = Decimal(str(data["price"]))
                if not ounce.is_finite() or ounce <= 0:
                    raise ValueError("Invalid gold price")
                gram = ounce / Decimal("31.1")
                quote = {
                    "ounce_usd": str(ounce),
                    "gram_24k_usd": str(gram),
                    "gram_21k_usd": str(gram * Decimal("0.875") / Decimal("0.995")),
                    "gram_18k_usd": str(gram * Decimal("0.75") / Decimal("0.995")),
                    "fetched_at": datetime.now(UTC).isoformat(),
                    "source_updated_at": data.get("updatedAt"),
                    "currency": "USD",
                }
                await redis.set(QUOTE_KEY, json.dumps(quote))
                return {**quote, "stale": False}
            except (httpx.HTTPError, ValueError, KeyError, TypeError, InvalidOperation):
                pass
        if quote:
            return {**quote, "stale": True}
        raise HTTPException(503, "Gold price unavailable; try again after 30 seconds")
    except RedisError as error:
        # Fail closed rather than make uncoordinated calls when shared cache fails.
        raise HTTPException(503, "Gold price cache unavailable") from error


def require_fresh_quote(quote: dict) -> None:
    if quote["stale"]:
        raise HTTPException(
            503, "A fresh gold quote is required to price this trade. Try again after 30 seconds."
        )


def price_per_gram(quote: dict, purity) -> Decimal:
    """USD per physical gram, rounded once for the permanent trade snapshot."""
    return (Decimal(quote["gram_24k_usd"]) * purchase_factor(purity)).quantize(
        Decimal("0.0001"), rounding=ROUND_HALF_UP
    )
