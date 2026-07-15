import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


# Build engine kwargs — sqlite needs check_same_thread=False; asyncpg needs none
_connect_args: dict = {}
if "sqlite" in settings.DATABASE_URL:
    _connect_args = {"check_same_thread": False}

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.APP_ENV == "development",
    connect_args=_connect_args,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def create_tables() -> None:
    """
    Create all tables on startup with retry logic.
    RDS takes a few seconds to accept connections on a cold start — retrying
    prevents the pod from crashing before the DB is ready.
    """
    max_attempts = 5
    backoff = 5  # seconds between retries

    for attempt in range(1, max_attempts + 1):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("✅ Database tables created/verified (attempt %d)", attempt)
            return
        except Exception as exc:
            if attempt < max_attempts:
                logger.warning(
                    "⚠️  DB not ready (attempt %d/%d): %s — retrying in %ds…",
                    attempt, max_attempts, exc, backoff,
                )
                await asyncio.sleep(backoff)
            else:
                logger.error(
                    "❌ Could not connect to DB after %d attempts: %s",
                    max_attempts, exc,
                )
                # Do NOT re-raise — let the app start anyway.
                # The health endpoint will report 'degraded' until DB is reachable.


async def get_db() -> AsyncSession:  # type: ignore[misc]
    """FastAPI dependency that yields a DB session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
