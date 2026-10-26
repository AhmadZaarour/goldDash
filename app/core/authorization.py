from typing import Annotated

from fastapi import Depends

from app.core.dependencies import require_role
from app.models.user import User, UserRole


AdminUser = Annotated[
    User,
    Depends(require_role(UserRole.ADMIN)),
]


CashierUser = Annotated[
    User,
    Depends(
        require_role(
            UserRole.ADMIN,
            UserRole.CASHIER,
        )
    ),
]


EmployeeUser = Annotated[
    User,
    Depends(
        require_role(
            UserRole.ADMIN,
            UserRole.EMPLOYEE,
        )
    ),
]