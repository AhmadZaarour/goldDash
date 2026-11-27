"""Admin-only record maintenance for registered application tables."""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, EmailStr, Field, JsonValue, TypeAdapter
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    Integer,
    Numeric,
    String,
    Table,
    func,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import AdminUser
from app.core.database import Base, get_db
from app.models.user import User, UserRole
from app.schemas.user import Username

router = APIRouter(prefix="/admin/data", tags=["Admin data"])
Database = Annotated[AsyncSession, Depends(get_db)]
PASSWORD_HASH = User.__table__.c.password_hash
USER_FIELDS = {
    "email": TypeAdapter(EmailStr),
    "username": TypeAdapter(Username),
    "role": TypeAdapter(UserRole),
}
FIELD_TYPES = {
    Boolean: "boolean",
    Integer: "integer",
    Numeric: "decimal",
    DateTime: "datetime",
    Date: "date",
    JSON: "json",
    String: "string",
}


class RecordKey(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: dict[str, JsonValue]


class RecordUpdate(RecordKey):
    changes: dict[str, JsonValue] = Field(min_length=1)


def table_by_name(name: str) -> Table:
    table = Base.metadata.tables.get(name)
    if table is None or not table.primary_key.columns:
        raise HTTPException(404, "Unknown application table")
    return table


def column_type(column: Column) -> str:
    return next(label for kind, label in FIELD_TYPES.items() if isinstance(column.type, kind))


def column_value(column: Column, value: JsonValue) -> Any:
    kind = column.type
    try:
        if value is None and column.nullable:
            return None
        if isinstance(kind, Boolean) and type(value) is bool:
            return value
        if isinstance(kind, Integer) and type(value) is int and -(2**31) <= value < 2**31:
            return value
        if isinstance(kind, Numeric) and type(value) in (str, int):
            decimal_type = Annotated[
                Decimal, Field(max_digits=kind.precision, decimal_places=kind.scale)
            ]
            return TypeAdapter(decimal_type).validate_python(value)
        if isinstance(kind, DateTime) and isinstance(value, str):
            timestamp = datetime.fromisoformat(value)
            if kind.timezone and timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=UTC)
            return timestamp
        if isinstance(kind, Date) and isinstance(value, str):
            return date.fromisoformat(value)
        if isinstance(kind, JSON) and value is not None:
            return value
        if isinstance(kind, String) and isinstance(value, str):
            if (kind.length is not None and len(value) > kind.length) or "\x00" in value:
                raise ValueError
            if isinstance(kind, Enum) and value not in kind.enums:
                raise ValueError
            if column.table is User.__table__:
                if column.name == "workspace_access" and value not in {
                    "showroom",
                    "factory",
                    "both",
                }:
                    raise ValueError
                validator = USER_FIELDS.get(column.name)
                if validator is not None:
                    return validator.validate_python(value)
            if column.name == "unit" and value not in {"factory", "showroom"}:
                raise ValueError
            return value
    except (ValueError, OverflowError):
        pass
    raise HTTPException(422, f"Invalid value for {column.name}")


def record_filter(table: Table, key: dict[str, JsonValue]):
    primary_key = table.primary_key.columns
    if key.keys() != set(primary_key.keys()):
        raise HTTPException(422, "Provide exactly the primary key fields for this table")
    return [column == column_value(column, key[column.name]) for column in primary_key]


def visible_columns(table: Table):
    return [column for column in table.columns if column is not PASSWORD_HASH]


def serialize_record(table: Table, values) -> dict:
    return {
        "key": jsonable_encoder({column.name: values[column.name] for column in table.primary_key}),
        "values": jsonable_encoder(dict(values), custom_encoder={Decimal: str}),
    }


async def protect_admin(db: AsyncSession, admin: User, target: int, changes: dict[str, Any] | None):
    # Serialize account edits affecting either participant. A request authorized
    # before another admin demotes it must recheck after taking the locks.
    users = User.__table__
    accounts = await db.execute(
        select(users.c.id, users.c.role, users.c.is_active)
        .where(users.c.id.in_({admin.id, target}))
        .order_by(users.c.id)
        .with_for_update()
    )
    if not any(
        account.id == admin.id and account.role == UserRole.ADMIN and account.is_active
        for account in accounts
    ):
        raise HTTPException(403, "An active admin account is required")
    if target == admin.id and (
        changes is None
        or changes.get("is_active") is False
        or changes.get("role", UserRole.ADMIN) != UserRole.ADMIN
    ):
        raise HTTPException(409, "You cannot delete, deactivate or demote your own admin account")


@router.get("")
async def list_tables(admin: AdminUser):
    return {
        "tables": [
            {
                "name": table.name,
                "columns": [
                    {
                        "name": column.name,
                        "type": column_type(column),
                        "nullable": column.nullable,
                        "primary_key": column.primary_key,
                        "editable": not column.primary_key,
                    }
                    for column in visible_columns(table)
                ],
            }
            for table in sorted(Base.metadata.tables.values(), key=lambda table: table.name)
            if table.primary_key.columns
        ]
    }


@router.get("/{table_name}")
async def list_records(
    table_name: str,
    db: Database,
    admin: AdminUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
    key: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
):
    table = table_by_name(table_name)
    predicate = []
    if key is not None:
        if len(table.primary_key.columns) != 1:
            raise HTTPException(422, "This table has more than one primary key field")
        column = next(iter(table.primary_key))
        value: JsonValue = key
        if isinstance(column.type, Integer):
            try:
                value = int(key)
            except ValueError as error:
                raise HTTPException(422, f"Invalid value for {column.name}") from error
        predicate = record_filter(table, {column.name: value})
    rows = await db.execute(
        select(*visible_columns(table))
        .where(*predicate)
        .order_by(*table.primary_key)
        .limit(limit)
        .offset(offset)
    )
    total = await db.scalar(select(func.count()).select_from(table).where(*predicate))
    return {"items": [serialize_record(table, row) for row in rows.mappings()], "total": total}


@router.patch("/{table_name}")
async def update_record(table_name: str, data: RecordUpdate, db: Database, admin: AdminUser):
    table = table_by_name(table_name)
    predicate = record_filter(table, data.key)
    values = {}
    for name, value in data.changes.items():
        column = table.columns.get(name)
        if column is None or column.primary_key or column is PASSWORD_HASH:
            raise HTTPException(422, f"Field {name} cannot be edited")
        values[name] = column_value(column, value)
    if table is User.__table__:
        await protect_admin(db, admin, int(data.key["id"]), values)
    result = await db.execute(
        table.update().where(*predicate).values(values).returning(*visible_columns(table))
    )
    row = result.mappings().one_or_none()
    if row is None:
        raise HTTPException(404, "Record no longer exists")
    await db.commit()
    return serialize_record(table, row)


@router.delete("/{table_name}", status_code=204)
async def delete_record(
    table_name: str, data: Annotated[RecordKey, Body()], db: Database, admin: AdminUser
) -> Response:
    table = table_by_name(table_name)
    predicate = record_filter(table, data.key)
    if table is User.__table__:
        await protect_admin(db, admin, int(data.key["id"]), None)
    result = await db.execute(table.delete().where(*predicate).returning(*table.primary_key))
    if result.first() is None:
        raise HTTPException(404, "Record no longer exists")
    await db.commit()
    return Response(status_code=204)
