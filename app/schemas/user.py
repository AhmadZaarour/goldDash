from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    ValidationInfo,
    field_validator,
)

from app.models.user import UserRole, workspace_for_role

Username = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]


class UserCreate(BaseModel):
    email: EmailStr = Field(max_length=255)
    username: Username
    password: str = Field(min_length=8, max_length=128)
    role: UserRole = UserRole.EMPLOYEE
    workspace_access: Literal["showroom", "factory", "both"] = "showroom"

    @field_validator("password")
    @classmethod
    def password_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Password must not be blank")
        return value


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    username: str
    role: UserRole
    workspace_access: str
    is_active: bool
    created_at: datetime

    @field_validator("workspace_access")
    @classmethod
    def effective_workspace(cls, value: str, info: ValidationInfo) -> str:
        role = info.data.get("role")
        return workspace_for_role(role) if role is not None else value
