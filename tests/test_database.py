"""
Tests targeting app/database.py to cover:
  - create_tables(): lines 26-27
  - get_db():        lines 32-38 (happy path + exception/rollback branch)
"""
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.database import Base, create_tables, get_db, AsyncSessionLocal

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# create_tables
# ---------------------------------------------------------------------------

class TestCreateTables:
    async def test_create_tables_runs_without_error(self):
        """create_tables() must complete successfully against an in-memory DB."""
        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            connect_args={"check_same_thread": False},
        )
        # Patch the module-level engine temporarily
        import app.database as db_module
        original_engine = db_module.engine
        db_module.engine = engine
        try:
            await create_tables()  # covers lines 26-27
        finally:
            db_module.engine = original_engine
            await engine.dispose()

    async def test_create_tables_creates_todos_table(self):
        """After create_tables(), the 'todos' table must exist."""
        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            connect_args={"check_same_thread": False},
        )
        import app.database as db_module
        original_engine = db_module.engine
        db_module.engine = engine
        try:
            await create_tables()
            async with engine.connect() as conn:
                result = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
                tables = [row[0] for row in result.fetchall()]
            assert "todos" in tables
        finally:
            db_module.engine = original_engine
            await engine.dispose()


# ---------------------------------------------------------------------------
# get_db  — happy path (yield + commit)
# ---------------------------------------------------------------------------

class TestGetDb:
    async def test_get_db_yields_session(self):
        """get_db() must yield an AsyncSession."""
        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            connect_args={"check_same_thread": False},
        )
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        from sqlalchemy.ext.asyncio import async_sessionmaker
        import app.database as db_module
        original_factory = db_module.AsyncSessionLocal
        db_module.AsyncSessionLocal = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        try:
            gen = get_db()
            session = await gen.__anext__()
            assert isinstance(session, AsyncSession)
            # Drive the generator to completion (simulates happy-path commit)
            try:
                await gen.aclose()
            except StopAsyncIteration:
                pass
        finally:
            db_module.AsyncSessionLocal = original_factory
            await engine.dispose()

    async def test_get_db_rollback_on_exception(self):
        """get_db() must rollback and re-raise when the consumer raises."""
        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            connect_args={"check_same_thread": False},
        )
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        from sqlalchemy.ext.asyncio import async_sessionmaker
        import app.database as db_module
        original_factory = db_module.AsyncSessionLocal
        db_module.AsyncSessionLocal = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        try:
            gen = get_db()
            session = await gen.__anext__()  # covers lines 32-35 (enter)
            assert isinstance(session, AsyncSession)
            # Simulate a consumer exception — covers the except/rollback branch (36-38)
            with pytest.raises(RuntimeError, match="simulated failure"):
                await gen.athrow(RuntimeError("simulated failure"))
        finally:
            db_module.AsyncSessionLocal = original_factory
            await engine.dispose()
