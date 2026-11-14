from datetime import datetime
from decimal import Decimal

from fastapi import HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import paginate
from app.core.workspace import active_unit
from app.models import Location, Supplier
from app.models.cashLedger import CashEntry
from app.models.goldPurities import GoldPurity
from app.models.inventoryBalance import InventoryBalance
from app.models.supplierLedger import SupplierLedgerEntry
from app.schemas.supplier_ledger import ReversalCreate, SettlementCreate
from app.services.gold_conversion import canonical_purity, grams24, purchase_factor
from app.services.gold_price import get_quote, price_per_gram, require_fresh_quote
from app.services.settlement_resources import available_cash, move_resources
from app.services.transaction_validation import require_active_location, require_active_supplier
from app.services.workspace_stock import value4


async def post_entry(
    db: AsyncSession,
    *,
    supplier_id: int,
    purity_id: int | None,
    gold_grams,
    making_usd,
    source_key: str,
    kind: str,
    created_by: int,
    purchase_id: int | None = None,
    sale_id: int | None = None,
    gold_24k: Decimal | None = None,
    valuation_factor: Decimal | None = None,
):
    """Post within the caller's transaction; never commit part of an invoice."""
    gold, usd = Decimal(str(gold_grams)), Decimal(str(making_usd))
    if gold == 0 and usd == 0:
        return
    factor = valuation_factor or Decimal(1)
    if gold_24k is None:
        if gold:
            purity = await db.get(GoldPurity, purity_id)
            if purity is None:
                raise ValueError("Purity not found")
            factor = purchase_factor(purity)
        gold_24k = grams24(gold, factor)
    entry = SupplierLedgerEntry(
        gold_24k=gold_24k,
        valuation_factor=factor,
        supplier_id=supplier_id,
        purity_id=purity_id,
        gold_grams=gold,
        making_usd=usd,
        source_key=source_key,
        kind=kind,
        created_by=created_by,
        purchase_id=purchase_id,
        sale_id=sale_id,
    )
    db.add(entry)
    return entry


async def supplier_balance(db: AsyncSession, supplier_id: int):
    rows = await db.execute(
        select(
            SupplierLedgerEntry.purity_id,
            func.sum(SupplierLedgerEntry.gold_grams),
            func.sum(SupplierLedgerEntry.making_usd),
        )
        .where(SupplierLedgerEntry.supplier_id == supplier_id)
        .group_by(SupplierLedgerEntry.purity_id)
    )
    total24 = await db.scalar(
        select(func.coalesce(func.sum(SupplierLedgerEntry.gold_24k), 0)).where(
            SupplierLedgerEntry.supplier_id == supplier_id
        )
    )
    gold, usd = {}, Decimal("0")
    for purity_id, grams, making in rows:
        if purity_id is not None:
            gold[purity_id] = grams
        usd += making
    return {
        "supplier_id": supplier_id,
        "gold_grams_by_purity": gold,
        "making_usd": usd,
        "gold_24k": total24,
        "is_settled": usd == 0 and total24 == 0,
    }


async def availability_service(
    supplier_id: int, db: AsyncSession, location_id: int, placement: str
):
    if await db.get(Supplier, supplier_id) is None:
        raise HTTPException(404, "Supplier not found")
    if await db.get(Location, location_id) is None:
        raise HTTPException(404, "Location not found")
    rows = await db.execute(
        select(InventoryBalance.purity_id, InventoryBalance.total_weight).where(
            InventoryBalance.location_id == location_id, InventoryBalance.placement == placement
        )
    )
    return {
        "cash_usd": await available_cash(db, location_id),
        "gold_grams_by_purity": dict(rows.all()),
    }


async def get_balance_service(supplier_id: int, db: AsyncSession):
    if await db.get(Supplier, supplier_id) is None:
        raise HTTPException(404, "Supplier not found")
    return await supplier_balance(db, supplier_id)


async def settle_service(supplier_id: int, data: SettlementCreate, db: AsyncSession, user_id: int):
    try:
        # Match trading lock order: location, then supplier, then stock.
        await require_active_location(db, data.location_id, exclusive=True)
        await require_active_supplier(db, supplier_id, exclusive=True)
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
    physical_purity = await db.get(GoldPurity, data.purity_id) if data.purity_id else None
    if data.purity_id and physical_purity is None:
        raise HTTPException(404, "Purity not found")
    canonical = await canonical_purity(db)
    factor = physical_purity.repayment_factor if physical_purity else Decimal(1)
    debt_gold = grams24(
        data.gold_grams * factor
        + (data.cash_gold_usd / data.gold_price_usd if data.cash_gold_usd else Decimal(0)),
        Decimal(1),
    )
    if not debt_gold and (not data.making_usd):
        raise HTTPException(422, "Settlement is below gold precision")
    sign = -1 if data.direction == "sent" else 1
    key = f"settlement:{active_unit()}:{supplier_id}:{data.idempotency_key}"
    if await db.scalar(select(SupplierLedgerEntry.id).where(SupplierLedgerEntry.source_key == key)):
        raise HTTPException(409, "Settlement key already used")
    before = await supplier_balance(db, supplier_id)
    if data.close_account and (
        before["making_usd"] + sign * data.making_usd != 0
        or before["gold_24k"] + sign * debt_gold != 0
    ):
        raise HTTPException(
            409, "Account can only be settled when USD and 24K-equivalent gold are zero"
        )
    stock_value = None
    recorded_price = data.gold_price_usd
    try:
        if data.gold_grams and data.direction == "received":
            if recorded_price is None:
                quote = await get_quote()
                require_fresh_quote(quote)
                recorded_price = Decimal(quote["gram_24k_usd"])
            stock_value = value4(
                data.gold_grams
                * price_per_gram({"gram_24k_usd": str(recorded_price)}, physical_purity)
            )
        stock_value = await move_resources(
            db,
            location_id=data.location_id,
            purity_id=data.purity_id,
            placement=data.placement,
            gold_delta=sign * data.gold_grams,
            gold_value_usd=stock_value,
            cash_delta=sign * (data.making_usd + data.cash_gold_usd),
        )
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
    entry = await post_entry(
        db,
        supplier_id=supplier_id,
        purity_id=canonical.id,
        gold_grams=sign * debt_gold,
        gold_24k=sign * debt_gold,
        valuation_factor=factor,
        making_usd=sign * data.making_usd,
        source_key=key,
        kind="settlement",
        created_by=user_id,
    )
    entry.physical_purity_id = data.purity_id
    entry.physical_gold_grams = sign * data.gold_grams
    entry.cash_gold_usd = sign * data.cash_gold_usd
    entry.gold_price_usd = recorded_price
    entry.stock_value_usd = stock_value
    entry.location_id = data.location_id
    entry.placement = data.placement if data.gold_grams else None
    try:
        if data.making_usd or data.cash_gold_usd:
            await db.flush()
            db.add(
                CashEntry(
                    location_id=data.location_id,
                    supplier_entry_id=entry.id,
                    kind=f"supplier_{data.direction}",
                    amount_usd=sign * (data.making_usd + data.cash_gold_usd),
                    created_by=user_id,
                )
            )
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        raise HTTPException(409, "Settlement conflict") from error
    return await supplier_balance(db, supplier_id)


async def history_service(
    supplier_id: int,
    db: AsyncSession,
    response: Response,
    limit: int = 50,
    offset: int = 0,
    purity_id: int | None = None,
    kind: str | None = None,
    from_at: datetime | None = None,
    to_at: datetime | None = None,
):
    if await db.get(Supplier, supplier_id) is None:
        raise HTTPException(404, "Supplier not found")
    if from_at and to_at and (from_at >= to_at):
        raise HTTPException(422, "from_at must be before to_at")
    statement = select(SupplierLedgerEntry).where(SupplierLedgerEntry.supplier_id == supplier_id)
    if purity_id is not None:
        statement = statement.where(SupplierLedgerEntry.purity_id == purity_id)
    if kind:
        statement = statement.where(SupplierLedgerEntry.kind == kind)
    if from_at:
        statement = statement.where(SupplierLedgerEntry.created_at >= from_at)
    if to_at:
        statement = statement.where(SupplierLedgerEntry.created_at < to_at)
    return await paginate(db, statement.order_by(SupplierLedgerEntry.id), response, limit, offset)


async def reverse_settlement_service(
    supplier_id: int, entry_id: int, data: ReversalCreate, db: AsyncSession, user_id: int
):
    original = await db.scalar(
        select(SupplierLedgerEntry).where(
            SupplierLedgerEntry.id == entry_id, SupplierLedgerEntry.supplier_id == supplier_id
        )
    )
    if original is None:
        raise HTTPException(404, "Ledger entry not found")
    if original.location_id is not None:
        await db.scalar(
            select(Location).where(Location.id == original.location_id).with_for_update()
        )
    await db.scalar(select(Supplier).where(Supplier.id == supplier_id).with_for_update())
    if original.kind != "settlement":
        raise HTTPException(
            409, "Only settlements can be reversed here; invoices require a return workflow"
        )
    if await db.scalar(
        select(SupplierLedgerEntry.id).where(SupplierLedgerEntry.reversal_of_id == original.id)
    ):
        raise HTTPException(409, "Settlement already reversed")
    if original.location_id is not None:
        try:
            await move_resources(
                db,
                location_id=original.location_id,
                purity_id=original.physical_purity_id or original.purity_id,
                placement=original.placement,
                gold_value_usd=original.stock_value_usd,
                gold_delta=-(
                    original.physical_gold_grams
                    if original.physical_gold_grams is not None
                    else original.gold_grams
                )
                if original.placement
                else Decimal(0),
                cash_delta=-(original.making_usd + (original.cash_gold_usd or Decimal(0))),
            )
        except ValueError as error:
            raise HTTPException(409, str(error)) from error
    reversal = SupplierLedgerEntry(
        supplier_id=supplier_id,
        purity_id=original.purity_id,
        source_key=f"reversal:{active_unit()}:{supplier_id}:{data.idempotency_key}",
        kind="reversal",
        gold_grams=-original.gold_grams,
        gold_24k=-original.gold_24k,
        valuation_factor=original.valuation_factor,
        physical_purity_id=original.physical_purity_id,
        physical_gold_grams=-original.physical_gold_grams
        if original.physical_gold_grams is not None
        else None,
        cash_gold_usd=-original.cash_gold_usd if original.cash_gold_usd is not None else None,
        gold_price_usd=original.gold_price_usd,
        stock_value_usd=original.stock_value_usd,
        making_usd=-original.making_usd,
        reversal_of_id=original.id,
        location_id=original.location_id,
        placement=original.placement,
        note=data.reason,
        created_by=user_id,
    )
    db.add(reversal)
    try:
        original_cash = await db.scalar(
            select(CashEntry).where(CashEntry.supplier_entry_id == original.id)
        )
        if original_cash is not None:
            await db.flush()
            db.add(
                CashEntry(
                    location_id=original_cash.location_id,
                    supplier_entry_id=reversal.id,
                    kind="supplier_reversal",
                    amount_usd=-original_cash.amount_usd,
                    created_by=user_id,
                )
            )
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        raise HTTPException(409, "Reversal conflict") from error
    await db.refresh(reversal)
    return reversal
