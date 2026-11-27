import re
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_access_token
from app.core.workspace import active_unit
from app.models.user import User, UserRole, workspace_for_role

bearer_scheme = HTTPBearer()
# Production and Servicing may read their shared location and purity choices.
EMPLOYEE_PATHS = {
    "GET": re.compile(
        r"/api/v1/(?:locations(?:/default|/[0-9]+)?|goldpurities(?:/[0-9]+)?|"
        r"operations/(?:workspaces|production(?:/[0-9]+)?)|servicing(?:/(?!sales$)[^/]+)?)"
    ),
    "POST": re.compile(
        r"/api/v1/(?:servicing|operations/(?:production|"
        r"weight-production(?:/[0-9]+/(?:steps|finish))?))"
    ),
    "PATCH": re.compile(r"/api/v1/servicing/[0-9]+"),
}


async def get_current_user(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials,
        Depends(bearer_scheme),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:

    token = credentials.credentials

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={
            "WWW-Authenticate": "Bearer",
        },
    )

    try:
        payload = decode_access_token(token)

        if payload.get("type") != "access":
            raise credentials_exception

        subject = payload.get("sub")

        if subject is None:
            raise credentials_exception

        user_id = int(subject)

    except (
        jwt.InvalidTokenError,
        ValueError,
        TypeError,
    ) as exc:
        raise credentials_exception from exc

    result = await db.execute(select(User).where(User.id == user_id))

    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )

    path = request.url.path
    account_route = path.startswith("/api/v1/auth/") or path == "/api/v1/users/me"
    if user.role != UserRole.ADMIN and not account_route:
        if user.role not in {UserRole.CASHIER, UserRole.EMPLOYEE} or (
            active_unit() != workspace_for_role(user.role)
        ):
            raise HTTPException(403, "Your account does not have access to this workspace")
        if user.role == UserRole.EMPLOYEE:
            allowed = EMPLOYEE_PATHS.get(request.method)
            if allowed is None or not allowed.fullmatch(path):
                raise HTTPException(403, "Employees can only access Production and Servicing")
    return user


CurrentUser = Annotated[
    User,
    Depends(get_current_user),
]


def require_role(*roles: UserRole):

    async def role_dependency(
        current_user: CurrentUser,
    ) -> User:

        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )

        return current_user

    return role_dependency
