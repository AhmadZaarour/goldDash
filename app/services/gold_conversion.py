"""Exact commercial rules. Never use repayment factors to value new purchases."""

from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.goldPurities import GoldPurity

GRAM = Decimal("0.001")


def purchase_factor(purity: GoldPurity) -> Decimal:
    return Decimal(1) if purity.karat == 24 else Decimal(str(purity.purity)) / Decimal("99.5")


def grams24(weight: Decimal, factor: Decimal) -> Decimal:
    return (weight * factor).quantize(GRAM, rounding=ROUND_HALF_UP)


async def canonical_purity(db: AsyncSession) -> GoldPurity:
    # Migration creates the canonical 24K record; don't create catalog entries during trades.
    purity = await db.scalar(
        select(GoldPurity).where(GoldPurity.karat == 24).order_by(GoldPurity.id)
    )
    if purity is None:
        raise ValueError("Configure a 24K purity before trading")
    return purity


def allocate_charge(total: Decimal, weights: list[Decimal]) -> list[Decimal]:
    units = int(total * 1000)
    raw = [Decimal(units) * weight / sum(weights) for weight in weights]
    allocated = [int(value) for value in raw]
    order = sorted(range(len(raw)), key=lambda i: (-(raw[i] - allocated[i]), i))
    for index in order[: units - sum(allocated)]:
        allocated[index] += 1
    return [Decimal(value) / 1000 for value in allocated]
