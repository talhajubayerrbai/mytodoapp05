import os
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db

router = APIRouter()


@router.get("/info", summary="API metadata and DB health")
async def api_info(db: AsyncSession = Depends(get_db)) -> dict:
    db_status = "unavailable"
    try:
        await db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        db_status = "error"

    return {
        "app": "mytodoapp05-dev",
        "version": "2.0.0",
        "description": "Production-grade Todo API",
        "db": db_status,
        "env": os.getenv("APP_ENV", "development"),
        "docs": "/docs",
        "redoc": "/redoc",
    }
