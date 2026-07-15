import time
from fastapi import APIRouter
from sqlalchemy import text

from app.database import engine

router = APIRouter()
_start = time.time()


@router.get("", summary="Liveness + DB connectivity check")
async def health_check() -> dict:
    """
    Always returns HTTP 200.
    - status/database = 'ok'       → app + DB are healthy
    - status/database = 'degraded' → app is alive but DB unreachable
    ALB health checks require 2xx; a DB hiccup must never make the pod
    appear unhealthy to the load balancer.
    """
    db_ok = False
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    return {
        "status": "ok" if db_ok else "degraded",
        "uptime": round(time.time() - _start, 1),
        "database": "ok" if db_ok else "error",
    }
