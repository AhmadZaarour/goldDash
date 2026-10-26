import asyncio
import getpass

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.user import User, UserRole


async def create_admin() -> None:
    email = input("Admin email: ").strip().lower()
    username = input("Admin username: ").strip()
    password = getpass.getpass("Admin password: ")
    confirm_password = getpass.getpass("Confirm password: ")

    if password != confirm_password:
        print("Passwords do not match.")
        return

    async with AsyncSessionLocal() as db:

        existing_user = await db.scalar(
            select(User).where(
                User.email == email,
            )
        )

        if existing_user:
            print("A user with this email already exists.")
            return

        admin = User(
            email=email,
            username=username,
            password_hash=hash_password(password),
            role=UserRole.ADMIN,
            is_active=True,
        )

        db.add(admin)

        await db.commit()
        print(f"Admin user '{username}' created successfully.")

if __name__ == "__main__":
    asyncio.run(create_admin())