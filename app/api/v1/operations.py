"""Workspace setup, production and paired Factory/Showroom accounting."""

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import AdminUser, EmployeeUser
from app.core.database import get_db
from app.core.dependencies import CurrentUser
from app.core.pagination import paginate
from app.core.workspace import active_unit, in_workspace, require_workspace
from app.models import (
    CashEntry,
    CashReconciliation,
    InventoryBalance,
    InventoryItem,
    InventoryMovement,
    InventoryService,
    InventoryStock,
    ItemReturn,
    PhotoUpload,
    Purchase,
    PurchaseItem,
    PurchaseStock,
    Sale,
    SaleItem,
    SaleStock,
    StockTransferRecord,
    SupplierLedgerEntry,
)
from app.models.operations import (
    InternalInvoice,
    InternalPayment,
    OperationDocument,
    ProductionBatch,
    ProductionPiece,
)
from app.schemas.operations import (
    CapitalCreate,
    CashTransferCreate,
    GoldTransferCreate,
    InternalInvoiceCreate,
    InternalPaymentCreate,
    LegacyAssignCreate,
    ProductionCreate,
    ReverseCreate,
    StaffWorkspaceUpdate,
    StockValuationCreate,
    SupplierItemSaleCreate,
)
from app.services import operations_service as service
from app.services.idempotency import IdempotencyKey, claim_operation, complete_operation
from app.services.workspace_stock import lock_locations

router = APIRouter(prefix="/operations", tags=["Workspaces and production"])
Database = Annotated[AsyncSession, Depends(get_db)]


class OperationResult(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: int
    kind: str
    message: str


def record(row):
    return {
        column.name: str(value)
        if isinstance(value := getattr(row, column.name), Decimal)
        else value
        for column in row.__table__.columns
    }


async def execute(db, user, name, key, data, action, *, paired=False):
    receipt, replayed = await claim_operation(db, user.id, name, key, data)
    if replayed:
        return OperationResult.model_validate(receipt.response_data)
    try:
        with in_workspace(None if paired else active_unit()):
            result = OperationResult.model_validate(await action())
            await complete_operation(db, receipt, result)
        return result
    except ValueError as error:
        await db.rollback()
        raise HTTPException(409, str(error)) from error


@router.get("/workspaces")
async def workspaces(user: CurrentUser):
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


@router.get("/overview")
async def overview(db: Database, user: CurrentUser, location_id: int | None = Query(None, gt=0)):
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


@router.post("/opening", response_model=OperationResult, status_code=201)
async def opening(data: CapitalCreate, db: Database, user: AdminUser, key: IdempotencyKey):
    unit = active_unit()
    return await execute(
        db, user, "opening", key, data, lambda: service.capital(db, data, user.id, unit, "opening")
    )


@router.post("/capital", response_model=OperationResult, status_code=201)
async def capital(data: CapitalCreate, db: Database, user: AdminUser, key: IdempotencyKey):
    unit = active_unit()
    return await execute(
        db,
        user,
        "capital",
        key,
        data,
        lambda: service.capital(db, data, user.id, unit, "capital_in"),
    )


@router.post("/adjustments", response_model=OperationResult, status_code=201)
async def adjustments(data: CapitalCreate, db: Database, user: AdminUser, key: IdempotencyKey):
    unit = active_unit()
    return await execute(
        db,
        user,
        "adjustment",
        key,
        data,
        lambda: service.capital(db, data, user.id, unit, "adjustment"),
    )


@router.post("/stock-value", response_model=OperationResult, status_code=201)
async def stock_value(
    data: StockValuationCreate, db: Database, user: AdminUser, key: IdempotencyKey
):
    unit = active_unit()
    return await execute(
        db, user, "stock:value", key, data, lambda: service.value_stock(db, data, user.id, unit)
    )


@router.post("/cash-transfers", response_model=OperationResult, status_code=201)
async def cash_transfer(
    data: CashTransferCreate, db: Database, user: AdminUser, key: IdempotencyKey
):
    unit = active_unit()
    return await execute(
        db,
        user,
        "cash:transfer",
        key,
        data,
        lambda: service.transfer_cash(db, data, user.id, unit),
        paired=True,
    )


@router.post("/gold-transfers", response_model=OperationResult, status_code=201)
async def gold_transfer(
    data: GoldTransferCreate, db: Database, user: AdminUser, key: IdempotencyKey
):
    unit = active_unit()
    return await execute(
        db,
        user,
        "gold:transfer",
        key,
        data,
        lambda: service.transfer_gold(db, data, user.id, unit),
        paired=True,
    )


@router.get("/history")
async def history(
    db: Database,
    response: Response,
    user: CurrentUser,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
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


@router.post("/production", response_model=OperationResult, status_code=201)
async def production(data: ProductionCreate, db: Database, user: EmployeeUser, key: IdempotencyKey):
    require_workspace("factory")
    return await execute(
        db, user, "production", key, data, lambda: service.production(db, data, user.id)
    )


@router.get("/production")
async def production_history(
    db: Database,
    response: Response,
    user: CurrentUser,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    rows = await paginate(
        db, select(ProductionBatch).order_by(ProductionBatch.id.desc()), response, limit, offset
    )
    return [record(row) for row in rows]


@router.get("/production/{batch_id}")
async def production_detail(batch_id: int, db: Database, user: CurrentUser):
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


@router.post("/internal-invoices", response_model=OperationResult, status_code=201)
async def internal_invoice(
    data: InternalInvoiceCreate, db: Database, user: AdminUser, key: IdempotencyKey
):
    require_workspace("factory")
    return await execute(
        db,
        user,
        "internal:invoice",
        key,
        data,
        lambda: service.internal_invoice(db, data, user.id),
        paired=True,
    )


@router.get("/internal-invoices")
async def internal_invoices(
    db: Database,
    response: Response,
    user: CurrentUser,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    rows = await paginate(
        db, select(InternalInvoice).order_by(InternalInvoice.id.desc()), response, limit, offset
    )
    return [record(row) for row in rows]


@router.get("/internal-balance")
async def internal_balance(db: Database, user: CurrentUser):
    result = await service.internal_balance(db)
    return {
        key: str(value) if isinstance(value, Decimal) else value for key, value in result.items()
    }


@router.post("/internal-payments", response_model=OperationResult, status_code=201)
async def internal_payment(
    data: InternalPaymentCreate, db: Database, user: AdminUser, key: IdempotencyKey
):
    return await execute(
        db,
        user,
        "internal:payment",
        key,
        data,
        lambda: service.internal_payment(db, data, user.id),
        paired=True,
    )


@router.get("/internal-payments")
async def internal_payments(
    db: Database,
    response: Response,
    user: CurrentUser,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    rows = await paginate(
        db, select(InternalPayment).order_by(InternalPayment.id.desc()), response, limit, offset
    )
    return [record(row) for row in rows]


@router.post("/supplier-item-sales", response_model=OperationResult, status_code=201)
async def supplier_item_sale(
    data: SupplierItemSaleCreate, db: Database, user: AdminUser, key: IdempotencyKey
):
    require_workspace("factory")
    return await execute(
        db, user, "supplier:items", key, data, lambda: service.supplier_item_sale(db, data, user.id)
    )


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


@router.get("/legacy")
async def legacy(
    db: Database,
    response: Response,
    user: AdminUser,
    kind: str = "purchase",
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
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


@router.post("/legacy/assign", response_model=OperationResult, status_code=201)
async def assign_legacy(
    data: LegacyAssignCreate, db: Database, user: AdminUser, key: IdempotencyKey
):
    async def action():
        model = LEGACY_MODELS[data.kind]
        row = await db.scalar(select(model).where(model.id == data.id).with_for_update())
        if row is None or row.unit is not None:
            raise ValueError("Choose an unassigned historical record")
        records = [row]
        if data.kind == "purchase":
            pieces = list(
                await db.scalars(select(PurchaseItem).where(PurchaseItem.purchase_id == row.id))
            )
            ids = [piece.id for piece in pieces]
            records += list(
                await db.scalars(
                    select(InventoryItem).where(InventoryItem.purchase_item_id.in_(ids))
                )
            )
            records += list(
                await db.scalars(select(PurchaseStock).where(PurchaseStock.purchase_id == row.id))
            )
            records += list(
                await db.scalars(
                    select(SupplierLedgerEntry).where(SupplierLedgerEntry.purchase_id == row.id)
                )
            )
            records += list(
                await db.scalars(select(CashEntry).where(CashEntry.purchase_id == row.id))
            )
            stock_ids = [r.id for r in records if isinstance(r, PurchaseStock)]
            records += list(
                await db.scalars(
                    select(InventoryStock).where(InventoryStock.purchase_stock_id.in_(stock_ids))
                )
            )
        if data.kind == "sale":
            records += list(await db.scalars(select(SaleItem).where(SaleItem.sale_id == row.id)))
            records += list(await db.scalars(select(SaleStock).where(SaleStock.sale_id == row.id)))
            records += list(await db.scalars(select(CashEntry).where(CashEntry.sale_id == row.id)))
            records += list(
                await db.scalars(
                    select(SupplierLedgerEntry).where(SupplierLedgerEntry.sale_id == row.id)
                )
            )
        if data.kind == "supplier_entry":
            records += list(
                await db.scalars(select(CashEntry).where(CashEntry.supplier_entry_id == row.id))
            )
        for item in records:
            if item.unit is not None and item.unit != data.unit:
                raise ValueError(
                    "A linked record belongs to another workspace; review the assignment"
                )
            item.unit = data.unit
        location_id = getattr(row, "location_id", None) or data.location_id
        if location_id is None:
            raise ValueError("Select a location for the ownership audit record")
        await lock_locations(db, location_id)
        # Classified bulk rows may need an explicit recorded value before production.
        doc = await service.document(
            db,
            unit=data.unit,
            kind="legacy_assignment",
            location_id=location_id,
            user_id=user.id,
            note=data.note,
            details={"kind": data.kind, "record_id": data.id},
        )
        return {
            "id": doc.id,
            "kind": "legacy_assignment",
            "message": "Historical ownership assigned",
        }

    return await execute(db, user, "legacy:assign", key, data, action, paired=True)


@router.post("/history/{operation_id}/reverse", response_model=OperationResult, status_code=201)
async def reverse_operation(
    operation_id: int, data: ReverseCreate, db: Database, user: AdminUser, key: IdempotencyKey
):
    unit = active_unit()
    return await execute(
        db,
        user,
        f"operation:reverse:{operation_id}",
        key,
        data,
        lambda: service.reverse_operation(db, operation_id, data.note, user.id, unit),
        paired=True,
    )


@router.post("/production/{batch_id}/reverse", response_model=OperationResult, status_code=201)
async def reverse_production(
    batch_id: int, data: ReverseCreate, db: Database, user: AdminUser, key: IdempotencyKey
):
    require_workspace("factory")
    return await execute(
        db,
        user,
        f"production:reverse:{batch_id}",
        key,
        data,
        lambda: service.reverse_production(db, batch_id, data.note, user.id),
    )


@router.post(
    "/internal-invoices/{invoice_id}/reverse", response_model=OperationResult, status_code=201
)
async def reverse_internal_invoice(
    invoice_id: int, data: ReverseCreate, db: Database, user: AdminUser, key: IdempotencyKey
):
    return await execute(
        db,
        user,
        f"internal:reverse:{invoice_id}",
        key,
        data,
        lambda: service.reverse_internal_invoice(db, invoice_id, data.note, user.id),
        paired=True,
    )


@router.post(
    "/internal-payments/{payment_id}/reverse", response_model=OperationResult, status_code=201
)
async def reverse_internal_payment(
    payment_id: int, data: ReverseCreate, db: Database, user: AdminUser, key: IdempotencyKey
):
    return await execute(
        db,
        user,
        f"internal:payment:reverse:{payment_id}",
        key,
        data,
        lambda: service.reverse_internal_payment(db, payment_id, data.note, user.id),
        paired=True,
    )


@router.get("/profit")
async def profit(
    db: Database,
    user: AdminUser,
    month: str = Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    company: bool = False,
    location_id: int | None = Query(None, gt=0),
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


@router.get("/internal-resources")
async def internal_resources(
    db: Database, user: AdminUser, unit: str, location_id: int = Query(gt=0)
):
    if unit not in {"factory", "showroom"}:
        raise HTTPException(422, "Choose Factory or Showroom")
    with in_workspace(unit):
        return await overview(db, user, location_id)


@router.patch("/staff/{user_id}")
async def staff_workspace(
    user_id: int, data: "StaffWorkspaceUpdate", db: Database, user: AdminUser
):
    from app.models import User

    staff = await db.get(User, user_id)
    if staff is None:
        raise HTTPException(404, "Staff account not found")
    staff.workspace_access = data.workspace_access
    await db.commit()
    return {"id": staff.id, "workspace_access": staff.workspace_access}


@router.get("/staff")
async def staff_list(
    db: Database,
    response: Response,
    user: AdminUser,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    from app.models import User
    from app.schemas.user import UserResponse

    rows = await paginate(db, select(User).order_by(User.id), response, limit, offset)
    return [UserResponse.model_validate(row).model_dump(mode="json") for row in rows]
