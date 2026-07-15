"""
Shared pytest fixtures for the Todo app test suite.

Strategy: each test gets its own in-memory SQLite engine so there is zero
state bleed between tests.  Using a fresh engine per test (rather than a
shared engine + savepoint rollback) is the most reliable approach with
aiosqlite, which does not support true nested transactions / SAVEPOINTs.
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.database import Base, get_db
from app.main import app


# ---------------------------------------------------------------------------
# Per-test in-memory SQLite engine (fresh schema every test)
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture()
async def engine():
    """
    Create a brand-new in-memory SQLite engine for each test, build the
    schema, yield it, then dispose — guarantees full isolation.
    """
    _engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        echo=False,
    )
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield _engine
    await _engine.dispose()


@pytest_asyncio.fixture()
async def db_session(engine):
    """
    Yield an AsyncSession bound to the per-test engine.
    The session is closed (not rolled back) after each test; isolation is
    guaranteed because the engine itself is discarded.
    """
    factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with factory() as session:
        yield session


# ---------------------------------------------------------------------------
# Async HTTP client with DB override
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture()
async def client(db_session):
    """
    Async HTTP client pointed at the FastAPI app with the DB dependency
    overridden to use the isolated test session.
    """
    async def _override_get_db():
        # Wrap in a try/commit/rollback so the router's commit() still works
        try:
            yield db_session
            await db_session.commit()
        except Exception:
            await db_session.rollback()
            raise

    app.dependency_overrides[get_db] = _override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()
