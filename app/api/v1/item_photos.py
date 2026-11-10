"""Authenticated, locally persisted item photos; no third-party storage required."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from app.api.v1.inventory_operations import Database
from app.core.dependencies import CurrentUser
from app.core.workspace import active_unit
from app.models.inventoryItem import InventoryItem
from app.models.user import User
from app.schemas.inventory import InventoryItemResponse
from app.services.item_photos_service import (
    stage_photo_service,
    upload_photo_service,
    read_item_photo_service,
)

router = APIRouter(tags=["Item photos"])

async def photo_user(user: CurrentUser) -> User:
    if user.role not in {"admin", "cashier"} and not (
        active_unit() == "factory" and user.role == "employee"
    ):
        raise HTTPException(403, "Insufficient permissions")
    return user


PhotoUser = Annotated[User, Depends(photo_user)]


@router.post("/purchases/photos", status_code=201)
async def stage_photo(request: Request, db: Database, user: PhotoUser) -> dict[str, str]:
    return await stage_photo_service(request, db, user)

@router.post("/inventory/items/{item_id}/photo", response_model=InventoryItemResponse)
async def upload_photo(item_id: int, request: Request, db: Database, user: PhotoUser) -> InventoryItem:
    return await upload_photo_service(item_id, request, db, user)


@router.get("/media/items/{filename}", name="read_item_photo")
async def read_item_photo(filename: str, user: CurrentUser, db: Database) -> FileResponse:
    return await read_item_photo_service(filename, user, db)
