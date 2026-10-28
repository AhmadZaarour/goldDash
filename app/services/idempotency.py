import hashlib
import json
from decimal import Decimal
from typing import Annotated, Any

from fastapi import Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.operationReceipt import OperationReceipt

IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=100)]


def canonical(value: Any) -> Any:
    if isinstance(value, Decimal):
        return "0" if value == 0 else str(value.normalize())
    if isinstance(value, dict):
        return {key: canonical(item) for key, item in value.items()}
    if isinstance(value, list):
        return [canonical(item) for item in value]
    return value


async def claim_operation(
    db: AsyncSession, user_id: int, operation: str, key: str, payload: BaseModel
) -> tuple[OperationReceipt, bool]:
    if not key.strip():
        raise HTTPException(422, "Idempotency-Key must not be blank")
    data = payload.model_dump(exclude={"created_by", "created_at"})
    fingerprint = hashlib.sha256(
        json.dumps(canonical(data), sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
    receipt_id = await db.scalar(
        insert(OperationReceipt)
        .values(
            user_id=user_id,
            operation=operation,
            key=key,
            fingerprint=fingerprint,
        )
        .on_conflict_do_nothing(constraint="uq_operation_retry")
        .returning(OperationReceipt.id)
    )
    if receipt_id is not None:
        receipt = await db.get(OperationReceipt, receipt_id)
        return receipt, False
    # ON CONFLICT waits for the first transaction. Its completed response is now visible.
    receipt = await db.scalar(
        select(OperationReceipt).where(
            OperationReceipt.user_id == user_id,
            OperationReceipt.operation == operation,
            OperationReceipt.key == key,
        )
    )
    if receipt.fingerprint != fingerprint:
        raise HTTPException(409, "Idempotency-Key was already used with different request data")
    if receipt.response_data is None:
        raise HTTPException(409, "Operation result is unavailable; retry with the same key")
    return receipt, True


async def complete_operation(db: AsyncSession, receipt: OperationReceipt, response: BaseModel):
    receipt.response_data = response.model_dump(mode="json")
    await db.commit()
