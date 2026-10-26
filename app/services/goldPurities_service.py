from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.goldPurities import GoldPurity
from app.schemas.goldPurities import GoldPurityCreate, GoldPurityUpdate

async def create_gold_purity(
    db: AsyncSession,
    gold_purities_data: GoldPurityCreate,
) -> GoldPurity:

    existing_gold_purities = await db.scalar(
        select(GoldPurity).where(
            GoldPurity.name == gold_purities_data.name,
        )
    )

    if existing_gold_purities is not None:
        raise ValueError("Gold purity already exists")

    gold_purity = GoldPurity(
        name=gold_purities_data.name,
        karat=gold_purities_data.karat,
        purity=gold_purities_data.purity,
    )

    db.add(gold_purity)

    await db.commit()
    await db.refresh(gold_purity)

    return gold_purity

async def get_gold_purities(
        db: AsyncSession,
) -> list[GoldPurity]:

    gold_purities = await db.scalars(
        select(GoldPurity).order_by(GoldPurity.id)
    )

    return list(gold_purities.all())

async def get_gold_purity(
    db: AsyncSession,
    gold_purity_id: int,
) -> GoldPurity | None:

    return await db.scalar(
        select(GoldPurity).where(
            GoldPurity.id == gold_purity_id,
        )
    )

async def update_gold_purity(
    db: AsyncSession,
    gold_purity: GoldPurity,
    gold_purity_data: GoldPurityUpdate,
) -> GoldPurity:

    update_data = gold_purity_data.model_dump(
        exclude_unset=True,
    )

    if "name" in update_data:
        existing_gold_purity = await db.scalar(
            select(GoldPurity).where(
                GoldPurity.name == update_data["name"],
                GoldPurity.id != gold_purity.id,
            )
        )

        if existing_gold_purity is not None:
            raise ValueError("gold purity already exists")

    for field, value in update_data.items():
        setattr(gold_purity, field, value)

    await db.commit()
    await db.refresh(gold_purity)

    return gold_purity