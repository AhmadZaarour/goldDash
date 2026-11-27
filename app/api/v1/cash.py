from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import AwareDatetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import AdminUser, CashierUser
from app.core.database import get_db
from app.core.pagination import paginate
from app.models.cashLedger import CashEntry
from app.schemas.cash import (
    CashEntryResponse,
    CashOutflowCreate,
    CashOutflowDetails,
    CashSummaryResponse,
    ReconciliationCounts,
    ReconciliationCreate,
    ReconciliationResponse,
)
from app.services.cash_service import (
    correct_outflow,
    correct_reconciliation,
    period_statement,
    reconcile_service,
    reconciliations_service,
    record_outflow_service,
    summary_service,
)
from app.services.idempotency import IdempotencyKey

router = APIRouter(prefix="/cash", tags=["Cash"])
Database = Annotated[AsyncSession, Depends(get_db)]


@router.get("/entries", response_model=list[CashEntryResponse])
async def entries(
    db: Database,
    response: Response,
    user: CashierUser,
    location_id: int = Query(gt=0),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    from_at: AwareDatetime | None = None,
    to_at: AwareDatetime | None = None,
    kind: Literal[
        "sale",
        "service_sale",
        "refund",
        "supplier_sent",
        "supplier_received",
        "supplier_reversal",
        "expense",
        "withdrawal",
        "customer_purchase",
        "capital",
        "adjustment",
        "cash_transfer",
        "internal_payment",
        "production_cost",
    ]
    | None = None,
):
    if from_at and to_at and from_at >= to_at:
        raise HTTPException(422, "from_at must be before to_at")
    statement = period_statement(location_id, from_at, to_at)
    if kind is not None:
        statement = statement.where(CashEntry.kind == kind)
    return await paginate(
        db,
        statement.order_by(CashEntry.id),
        response,
        limit,
        offset,
    )


@router.get("/summary", response_model=CashSummaryResponse)
async def summary(
    db: Database,
    user: CashierUser,
    location_id: int = Query(gt=0),
    from_at: AwareDatetime | None = None,
    to_at: AwareDatetime | None = None,
) -> CashSummaryResponse:
    """
    Get a summary of cash entries for a given location and time period.
    """
    summary = await summary_service(db, location_id, from_at, to_at)
    return CashSummaryResponse(**summary)


@router.post("/reconciliations", response_model=ReconciliationResponse, status_code=201)
async def reconcile(
    data: ReconciliationCreate,
    db: Database,
    user: AdminUser,
) -> ReconciliationResponse:
    """
    Create a cash reconciliation record for a given location and time period.
    """
    record = await reconcile_service(data, db, user)
    return ReconciliationResponse.model_validate(record)


@router.get("/reconciliations", response_model=list[ReconciliationResponse])
async def reconciliations(
    db: Database,
    response: Response,
    user: AdminUser,
    location_id: int = Query(gt=0),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list[ReconciliationResponse]:
    """
    Get a list of cash reconciliation records for a given location.
    """
    result = await reconciliations_service(db, response, location_id, limit, offset)
    return [ReconciliationResponse.model_validate(record) for record in result]


@router.post("/outflows", response_model=CashEntryResponse, status_code=201)
async def record_outflow(
    data: CashOutflowCreate,
    db: Database,
    user: AdminUser,
    idempotency_key: IdempotencyKey,
) -> CashEntryResponse:
    """
    Record a cash outflow for a given location.
    """
    receipt = await record_outflow_service(data, db, user, idempotency_key)
    return receipt


@router.patch("/outflows/{entry_id}", response_model=CashEntryResponse)
async def update_outflow(entry_id: int, data: CashOutflowDetails, db: Database, user: AdminUser):
    return await correct_outflow(db, entry_id, data)


@router.delete("/outflows/{entry_id}", status_code=204)
async def delete_outflow(entry_id: int, db: Database, user: AdminUser):
    await correct_outflow(db, entry_id, None)


@router.patch("/reconciliations/{record_id}", response_model=ReconciliationResponse)
async def update_reconciliation(
    record_id: int, data: ReconciliationCounts, db: Database, user: AdminUser
):
    return await correct_reconciliation(db, record_id, data)


@router.delete("/reconciliations/{record_id}", status_code=204)
async def void_reconciliation(record_id: int, db: Database, user: AdminUser):
    await correct_reconciliation(db, record_id, None)
