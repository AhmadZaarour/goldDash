from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.router import api_router
from app.core.config import Settings, settings
from app.core.database import get_db
from app.core.redis import redis


def create_app(config: Settings | None = None) -> FastAPI:
    config = config or settings
    application = FastAPI(title=config.app_name, version=config.app_version)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=["X-Total-Count", "X-Limit", "X-Offset"],
    )

    @application.exception_handler(IntegrityError)
    async def integrity_conflict(request: Request, error: IntegrityError):
        return JSONResponse(
            status_code=409,
            content={"detail": "The operation conflicts with existing or referenced data"},
        )

    application.include_router(api_router)

    @application.get("/health")
    async def health_check() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/ready")
    async def readiness(db: AsyncSession = Depends(get_db)) -> dict[str, str]:
        try:
            await db.execute(text("SELECT 1"))
            await redis.ping()
        except (SQLAlchemyError, RedisError) as error:
            raise HTTPException(503, "A required service is unavailable") from error
        return {"status": "ready"}

    return application


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run("app.main:app")
