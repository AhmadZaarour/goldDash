from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator

from app.models.user import UserRole

Username = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]


class UserCreate(BaseModel):
    email: EmailStr = Field(max_length=255)
    username: Username
    password: str = Field(min_length=8, max_length=128)
    role: UserRole = UserRole.EMPLOYEE

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
    is_active: bool
    created_at: datetime
