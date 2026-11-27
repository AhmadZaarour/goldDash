from typing import Annotated

from pydantic import BaseModel, EmailStr, StringConstraints, model_validator

from app.schemas.user import Username


class LoginRequest(BaseModel):
    identifier: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
        | None
    ) = None
    email: EmailStr | None = None
    username: Username | None = None
    password: str

    @model_validator(mode="after")
    def require_login_identifier(self):
        fields = (self.identifier, self.email, self.username)
        if sum(value is not None for value in fields) != 1:
            raise ValueError("Provide exactly one of identifier, email or username")
        return self


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshTokenRequest(BaseModel):
    refresh_token: str
