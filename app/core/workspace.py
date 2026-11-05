"""Request-owned workspaces; physical locations are deliberately shared."""

from contextlib import contextmanager
from contextvars import ContextVar

from fastapi import HTTPException
from sqlalchemy import String, event
from sqlalchemy.orm import Mapped, Session, mapped_column, with_loader_criteria

workspace_context: ContextVar[str | None] = ContextVar("business_workspace", default=None)


def active_unit() -> str:
    return workspace_context.get() or "showroom"


class UnitOwned:
    unit: Mapped[str | None] = mapped_column(
        String(20), nullable=True, index=True, default=active_unit
    )


@contextmanager
def in_workspace(unit: str | None):
    token = workspace_context.set(unit)
    try:
        yield
    finally:
        workspace_context.reset(token)


def require_workspace(unit: str):
    if workspace_context.get() is not None and active_unit() != unit:
        raise HTTPException(403, f"This operation belongs to the {unit} workspace")


@event.listens_for(Session, "do_orm_execute")
def scope_reads(state):
    unit = workspace_context.get()
    if not state.is_select or unit is None:
        return
    if unit == "legacy":
        state.statement = state.statement.options(
            with_loader_criteria(UnitOwned, lambda cls: cls.unit.is_(None), include_aliases=True)
        )
    else:
        state.statement = state.statement.options(
            with_loader_criteria(UnitOwned, lambda cls: cls.unit == unit, include_aliases=True)
        )


@event.listens_for(Session, "before_flush")
def scope_writes(session, flush_context, instances):
    unit = workspace_context.get()
    if unit is None:
        return
    for record in session.new | session.dirty | session.deleted:
        if isinstance(record, UnitOwned):
            if record in session.new and record.unit is None:
                record.unit = unit
            if unit == "legacy" or record.unit != unit:
                raise HTTPException(403, "Use the workspace that owns this record")
