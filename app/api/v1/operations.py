"""HTTP validation and authorization for workspace operations."""

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import AdminUser, EmployeeUser
from app.core.database import get_db
from app.core.dependencies import CurrentUser
from app.core.workspace import active_unit, require_workspace
from app.schemas.operations import (
    CapitalCreate,
    CashTransferCreate,
    GoldTransferCreate,
    InternalInvoiceCreate,
    InternalPaymentCreate,
    LegacyAssignCreate,
    OperationResult,
    ProductionCreate,
    ReverseCreate,
    StaffWorkspaceUpdate,
    StockValuationCreate,
    SupplierItemSaleCreate,
)
from app.services import operations_query_service as queries
from app.services import operations_service as service
from app.services.idempotency import IdempotencyKey

router = APIRouter(prefix="/operations", tags=["Workspaces and production"])
Database = Annotated[AsyncSession, Depends(get_db)]


@router.get("/workspaces")
async def workspaces(user: CurrentUser):
    return await queries.workspaces(user)


@router.get("/overview")
async def overview(db: Database, user: CurrentUser, location_id: int | None = Query(None, gt=0)):
    return await queries.overview(db, user, location_id)


@router.post("/opening", response_model=OperationResult, status_code=201)
async def opening(data: CapitalCreate, db: Database, user: AdminUser, key: IdempotencyKey):
    unit = active_unit()
    return await service.execute(
        db,
        user.id,
        "opening",
        key,
        data,
        lambda: service.capital(db, data, user.id, unit, "opening"),
    )


@router.post("/capital", response_model=OperationResult, status_code=201)
async def capital(data: CapitalCreate, db: Database, user: AdminUser, key: IdempotencyKey):
    unit = active_unit()
    return await service.execute(
        db,
        user.id,
        "capital",
        key,
        data,
        lambda: service.capital(db, data, user.id, unit, "capital_in"),
    )


@router.post("/adjustments", response_model=OperationResult, status_code=201)
async def adjustments(data: CapitalCreate, db: Database, user: AdminUser, key: IdempotencyKey):
    unit = active_unit()
    return await service.execute(
        db,
        user.id,
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
    return await service.execute(
        db, user.id, "stock:value", key, data, lambda: service.value_stock(db, data, user.id, unit)
    )


@router.post("/cash-transfers", response_model=OperationResult, status_code=201)
async def cash_transfer(
    data: CashTransferCreate, db: Database, user: AdminUser, key: IdempotencyKey
):
    unit = active_unit()
    return await service.execute(
        db,
        user.id,
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
    return await service.execute(
        db,
        user.id,
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
    return await queries.history(db, response, limit, offset)


@router.post("/production", response_model=OperationResult, status_code=201)
async def production(data: ProductionCreate, db: Database, user: EmployeeUser, key: IdempotencyKey):
    require_workspace("factory")
    return await service.execute(
        db, user.id, "production", key, data, lambda: service.production(db, data, user.id)
    )


@router.get("/production")
async def production_history(
    db: Database,
    response: Response,
    user: CurrentUser,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    return await queries.production_history(db, response, limit, offset)


@router.get("/production/{batch_id}")
async def production_detail(batch_id: int, db: Database, user: CurrentUser):
    return await queries.production_detail(batch_id, db)


@router.post("/internal-invoices", response_model=OperationResult, status_code=201)
async def internal_invoice(
    data: InternalInvoiceCreate, db: Database, user: AdminUser, key: IdempotencyKey
):
    require_workspace("factory")
    return await service.execute(
        db,
        user.id,
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
    return await queries.internal_invoices(db, response, limit, offset)


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
    return await service.execute(
        db,
        user.id,
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
    return await queries.internal_payments(db, response, limit, offset)


@router.post("/supplier-item-sales", response_model=OperationResult, status_code=201)
async def supplier_item_sale(
    data: SupplierItemSaleCreate, db: Database, user: AdminUser, key: IdempotencyKey
):
    require_workspace("factory")
    return await service.execute(
        db,
        user.id,
        "supplier:items",
        key,
        data,
        lambda: service.supplier_item_sale(db, data, user.id),
    )


@router.get("/legacy")
async def legacy(
    db: Database,
    response: Response,
    user: AdminUser,
    kind: str = "purchase",
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    return await queries.legacy(db, response, kind, limit, offset)


@router.post("/legacy/assign", response_model=OperationResult, status_code=201)
async def assign_legacy(
    data: LegacyAssignCreate, db: Database, user: AdminUser, key: IdempotencyKey
):
    return await service.execute(
        db,
        user.id,
        "legacy:assign",
        key,
        data,
        lambda: service.assign_legacy(db, data, user.id),
        paired=True,
    )


@router.post("/history/{operation_id}/reverse", response_model=OperationResult, status_code=201)
async def reverse_operation(
    operation_id: int, data: ReverseCreate, db: Database, user: AdminUser, key: IdempotencyKey
):
    unit = active_unit()
    return await service.execute(
        db,
        user.id,
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
    return await service.execute(
        db,
        user.id,
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
    return await service.execute(
        db,
        user.id,
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
    return await service.execute(
        db,
        user.id,
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
    month: str = Query(pattern="^\\d{4}-(0[1-9]|1[0-2])$"),
    company: bool = False,
    location_id: int | None = Query(None, gt=0),
):
    return await queries.profit(db, month, company, location_id)


@router.get("/internal-resources")
async def internal_resources(
    db: Database, user: AdminUser, unit: str, location_id: int = Query(gt=0)
):
    return await queries.internal_resources(db, user, unit, location_id)


@router.patch("/staff/{user_id}")
async def staff_workspace(
    user_id: int, data: "StaffWorkspaceUpdate", db: Database, user: AdminUser
):
    return await queries.staff_workspace(user_id, data, db)


@router.get("/staff")
async def staff_list(
    db: Database,
    response: Response,
    user: AdminUser,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    return await queries.staff_list(db, response, limit, offset)
