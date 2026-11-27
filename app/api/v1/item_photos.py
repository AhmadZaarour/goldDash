"""Authenticated item photos persisted in local storage."""

from fastapi import APIRouter, Request, Response

from app.api.v1.inventory_operations import Database
from app.core.authorization import CashierUser
from app.core.dependencies import CurrentUser
from app.models.inventoryItem import InventoryItem
from app.schemas.inventory import InventoryItemResponse
from app.services.item_photos_service import (
    stage_photo_service,
    upload_photo_service,
    read_item_photo_service,
)

router = APIRouter(tags=["Item photos"])

@router.post("/purchases/photos", status_code=201)
async def stage_photo(request: Request, db: Database, user: CashierUser) -> dict[str, str]:
    return await stage_photo_service(request, db, user)

@router.post("/inventory/items/{item_id}/photo", response_model=InventoryItemResponse)
async def upload_photo(item_id: int, request: Request, db: Database, user: CashierUser) -> InventoryItem:
    return await upload_photo_service(item_id, request, db, user)


@router.get("/media/items/{filename}", name="read_item_photo")
async def read_item_photo(filename: str, user: CurrentUser, db: Database) -> Response:
    return await read_item_photo_service(filename, user, db)
