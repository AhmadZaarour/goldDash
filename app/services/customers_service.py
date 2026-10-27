from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customers import Customer
from app.schemas.customers import CustomerCreate, CustomerUpdate

async def create_customer(
        db: AsyncSession,
        customer_data: CustomerCreate
) -> Customer:

    existing_customer = await db.scalar(
        select(Customer).where(
            Customer.name == customer_data.name,
        )
    )

    if existing_customer is not None:
        raise ValueError("Customer name already exist")

    customer = Customer(
        name = customer_data.name,
        phone = customer_data.phone,
    )

    db.add(customer)

    await db.commit()
    await db.refresh(customer)

    return customer

async def get_customers(
        db: AsyncSession,
) -> list[Customer]:

    customers = await db.scalars(
        select(Customer).order_by(Customer.id)
    )

    return list(customers.all())

async def get_customer(
        db: AsyncSession,
        customer_id: int,
) -> Customer | None:

    return await db.scalar(
        select(Customer).where(
            Customer.id == customer_id
        )
    )

async def update_customer(
        db: AsyncSession,
        customer: Customer,
        customer_data: CustomerUpdate,
) -> Customer | None:

    update_data = customer_data.model_dump(
        exclude_unset=True,
    )

    if "name" in update_data:
        existing_customer = await db.scalar(
            select(Customer).where(
                Customer.name == update_data["name"],
                Customer.id != customer.id,
            )
        )

        if existing_customer is not None:
            raise ValueError("Customer name already exist")

    for field, value in update_data.items():
        setattr(customer, field, value)

    await db.commit()
    await db.refresh(customer)

    return customer
