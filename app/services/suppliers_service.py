from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.suppliers import Supplier
from app.schemas.suppliers import SupplierCreate, SupplierUpdate

async def create_supplier(
        db: AsyncSession,
        supplier_data: SupplierCreate
) -> Supplier:

    existing_supplier = await db.scalar(
        select(Supplier).where(
            Supplier.name == supplier_data.name,
        )
    )

    if existing_supplier is not None:
        raise ValueError("Customer name already exist")

    supplier = Supplier(
        name = supplier_data.name,
        phone = supplier_data.phone,
    )

    db.add(supplier)

    await db.commit()
    await db.refresh(supplier)
    return supplier

async def get_suppliers(
        db: AsyncSession,
) -> list[Supplier]:

    suppliers = await db.scalars(
        select(Supplier).order_by(Supplier.id)
    )

    return list(suppliers.all())

async def get_supplier(
        db: AsyncSession,
        supplier_id: int,
) -> Supplier | None:

    return await db.scalar(
        select(Supplier).where(
            Supplier.id == supplier_id
        )
    )

async def update_supplier(
        db: AsyncSession,
        supplier: Supplier,
        supplier_data: SupplierUpdate,
) -> Supplier | None:

    update_data = supplier_data.model_dump(
        exclude_unset=True,
    )

    if "name" in update_data:
        existing_supplier = await db.scalar(
            select(Supplier).where(
                Supplier.name == update_data["name"],
                Supplier.id != supplier.id,
            )
        )

        if existing_supplier is not None:
            raise ValueError("supplier name already exist")

    for field, value in update_data.items():
        setattr(supplier, field, value)

    await db.commit()
    await db.refresh(supplier)

    return supplier