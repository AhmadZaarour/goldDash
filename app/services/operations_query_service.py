"""Workspace queries, history and report serialization."""

from decimal import Decimal

from fastapi import HTTPException, Response
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import paginate
from app.core.workspace import active_unit, in_workspace
from app.models import (
    CashEntry,
    CashReconciliation,
    InventoryBalance,
    InventoryItem,
    InventoryMovement,
    InventoryService,
    ItemReturn,
    PhotoUpload,
    Purchase,
    Sale,
    StockTransferRecord,
    SupplierLedgerEntry,
    User,
)
from app.models.operations import (
    InternalInvoice,
    InternalPayment,
    OperationDocument,
    ProductionBatch,
    ProductionPiece,
)
from app.schemas.operations import StaffWorkspaceUpdate

LEGACY_MODELS = {
    "purchase": Purchase,
    "sale": Sale,
    "cash": CashEntry,
    "stock": InventoryBalance,
    "item": InventoryItem,
    "supplier_entry": SupplierLedgerEntry,
    "reconciliation": CashReconciliation,
    "return": ItemReturn,
    "movement": InventoryMovement,
    "service": InventoryService,
    "transfer": StockTransferRecord,
    "photo": PhotoUpload,
}


def record(row):
    return {
        column.name: str(value)
        if isinstance(value := getattr(row, column.name), Decimal)
        else value
        for column in row.__table__.columns
    }


async def workspaces(user: User):
    allowed = (
        ["showroom", "factory"]
        if user.role == "admin" or user.workspace_access == "both"
        else [user.workspace_access]
    )
    return {
        "units": allowed,
        "can_review_legacy": user.role == "admin",
        "active_unit": active_unit(),
    }


async def overview(db: AsyncSession, user: User, location_id: int | None = None):
    cash = select(func.coalesce(func.sum(CashEntry.amount_usd), 0))
    gold = select(InventoryBalance).order_by(
        InventoryBalance.location_id, InventoryBalance.purity_id, InventoryBalance.placement
    )
    pieces = (
        select(func.count()).select_from(InventoryItem).where(InventoryItem.status == "in_stock")
    )
    if location_id:
        cash = cash.where(CashEntry.location_id == location_id)
        gold = gold.where(InventoryBalance.location_id == location_id)
        pieces = pieces.where(InventoryItem.location_id == location_id)
    return {
        "unit": active_unit(),
        "cash_usd": str(await db.scalar(cash)) if user.role != "employee" else None,
        "available_pieces": await db.scalar(pieces),
        "bulk": [record(row) for row in await db.scalars(gold)],
    }


async def history(db: AsyncSession, response: Response, limit: int = 50, offset: int = 0):
    unit = active_unit()
    rows = await paginate(
        db,
        select(OperationDocument)
        .where(or_(OperationDocument.unit == unit, OperationDocument.other_unit == unit))
        .order_by(OperationDocument.id.desc()),
        response,
        limit,
        offset,
    )
    return [record(row) for row in rows]


async def production_history(
    db: AsyncSession, response: Response, limit: int = 50, offset: int = 0
):
    rows = await paginate(
        db, select(ProductionBatch).order_by(ProductionBatch.id.desc()), response, limit, offset
    )
    return [record(row) for row in rows]


async def production_detail(batch_id: int, db: AsyncSession):
    batch = await db.get(ProductionBatch, batch_id)
    if batch is None:
        raise HTTPException(404, "Production batch not found")
    pieces = list(
        await db.scalars(
            select(ProductionPiece)
            .where(ProductionPiece.batch_id == batch.id)
            .order_by(ProductionPiece.id)
        )
    )
    with in_workspace(None):
        inventory = list(
            await db.scalars(
                select(InventoryItem).where(
                    InventoryItem.production_piece_id.in_([piece.id for piece in pieces])
                )
            )
        )
    by_piece = {item.production_piece_id: item for item in inventory}
    return {
        **record(batch),
        "pieces": [
            {**record(row), "barcode": by_piece[row.id].barcode if row.id in by_piece else None}
            for row in pieces
        ],
    }


async def internal_invoices(db: AsyncSession, response: Response, limit: int = 50, offset: int = 0):
    rows = await paginate(
        db, select(InternalInvoice).order_by(InternalInvoice.id.desc()), response, limit, offset
    )
    return [record(row) for row in rows]


async def internal_payments(db: AsyncSession, response: Response, limit: int = 50, offset: int = 0):
    rows = await paginate(
        db, select(InternalPayment).order_by(InternalPayment.id.desc()), response, limit, offset
    )
    return [record(row) for row in rows]


async def legacy(
    db: AsyncSession, response: Response, kind: str = "purchase", limit: int = 50, offset: int = 0
):
    model = LEGACY_MODELS.get(kind)
    if model is None:
        raise HTTPException(422, "Unknown historical record type")
    with in_workspace(None):
        rows = await paginate(
            db,
            select(model).where(model.unit.is_(None)).order_by(model.id),
            response,
            limit,
            offset,
        )
    return [record(row) for row in rows]


async def profit(
    db: AsyncSession, month: str, company: bool = False, location_id: int | None = None
):
    from app.services.workspace_reports import profit_report

    unit = "company" if company else active_unit()
    if unit == "legacy":
        raise HTTPException(
            409, "Classify historical ownership before using workspace profit reports"
        )
    try:
        result = await profit_report(db, month, unit, location_id)
    except (ValueError, OverflowError) as error:
        raise HTTPException(422, "Invalid reporting month") from error
    return {
        key: str(value) if isinstance(value, Decimal) else value for key, value in result.items()
    }


async def internal_resources(db: AsyncSession, user: User, unit: str, location_id: int):
    if unit not in {"factory", "showroom"}:
        raise HTTPException(422, "Choose Factory or Showroom")
    with in_workspace(unit):
        return await overview(db, user, location_id)


async def staff_workspace(user_id: int, data: StaffWorkspaceUpdate, db: AsyncSession):
    staff = await db.get(User, user_id)
    if staff is None:
        raise HTTPException(404, "Staff account not found")
    staff.workspace_access = data.workspace_access
    await db.commit()
    return {"id": staff.id, "workspace_access": staff.workspace_access}


async def staff_list(db: AsyncSession, response: Response, limit: int = 50, offset: int = 0):
    from app.schemas.user import UserResponse

    rows = await paginate(db, select(User).order_by(User.id), response, limit, offset)
    return [UserResponse.model_validate(row).model_dump(mode="json") for row in rows]
