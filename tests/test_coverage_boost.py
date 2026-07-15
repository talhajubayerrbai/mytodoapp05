"""
Targeted tests to cover branches missed by the main suite:

  - /health/  DB-error path         → health.py lines 17-21
  - /api/info DB-error path         → api.py   lines 16-20
  - Global exception handler        → main.py  line 61
  - Root / SPA fallback             → main.py  lines 71-78, 91
  - todos: update with priority=None → todos.py lines 113-117, 121
  - todos: flush / search ilike     → todos.py lines 81, 100, 131, 134, 145-146
"""
import pathlib
import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.database import get_db

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _create(client: AsyncClient, **kwargs) -> dict:
    payload = {"title": "Coverage todo", "priority": "medium", **kwargs}
    resp = await client.post("/todos/", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Health endpoint — DB error branch
# ---------------------------------------------------------------------------

class TestHealthDbError:
    async def test_health_degraded_when_db_fails(self, client):
        """Force the DB execute to raise so the except branch runs."""
        original_override = app.dependency_overrides.get(get_db)

        async def _broken_db():
            mock = AsyncMock(spec=AsyncSession)
            mock.execute.side_effect = Exception("DB connection lost")
            yield mock

        app.dependency_overrides[get_db] = _broken_db
        try:
            resp = await client.get("/health/")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "degraded"
            assert data["database"] == "error"
        finally:
            if original_override:
                app.dependency_overrides[get_db] = original_override
            else:
                app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# API info endpoint — DB error branch
# ---------------------------------------------------------------------------

class TestApiInfoDbError:
    async def test_api_info_db_unavailable_when_fails(self, client):
        """Force the DB execute to raise so the except branch runs."""
        original_override = app.dependency_overrides.get(get_db)

        async def _broken_db():
            mock = AsyncMock(spec=AsyncSession)
            mock.execute.side_effect = Exception("DB connection lost")
            yield mock

        app.dependency_overrides[get_db] = _broken_db
        try:
            resp = await client.get("/api/info")
            assert resp.status_code == 200
            data = resp.json()
            assert data["db"] == "error"
        finally:
            if original_override:
                app.dependency_overrides[get_db] = original_override
            else:
                app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Global exception handler — main.py line 61
# ---------------------------------------------------------------------------

class TestGlobalExceptionHandler:
    async def test_global_handler_returns_500(self):
        """Register a temp route that raises, hit it, confirm 500 JSON."""
        from fastapi import FastAPI
        from app.main import global_exception_handler

        mini = FastAPI()
        mini.add_exception_handler(Exception, global_exception_handler)

        @mini.get("/boom")
        async def boom():
            raise RuntimeError("kaboom")

        # raise_server_exceptions=False is passed to ASGITransport so that
        # httpx lets the ASGI app's exception handler run and return the 500
        # JSON response instead of re-raising the RuntimeError to the test.
        # In httpx >= 0.28 this argument belongs on ASGITransport, not on
        # AsyncClient.
        async with AsyncClient(
            transport=ASGITransport(app=mini, raise_server_exceptions=False),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get("/boom")
        assert resp.status_code == 500
        assert resp.json()["detail"] == "An internal server error occurred."


# ---------------------------------------------------------------------------
# Root / SPA endpoint — main.py lines 71-78, 91
# ---------------------------------------------------------------------------

class TestRootEndpoint:
    async def test_root_returns_html_when_index_exists(self, client):
        """index.html exists in public/ → should return 200 HTML."""
        resp = await client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    async def test_root_returns_fallback_when_no_index(self):
        """Patch pathlib.Path.exists to return False → fallback HTML."""
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            with patch("pathlib.Path.exists", return_value=False):
                resp = await ac.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "running" in resp.text.lower()


# ---------------------------------------------------------------------------
# Todos router — uncovered branches
# ---------------------------------------------------------------------------

class TestTodosUncoveredBranches:
    async def test_update_without_priority_field(self, client):
        """PATCH with no priority field → priority branch skipped (line 117)."""
        created = await _create(client, title="no-priority patch", priority="high")
        resp = await client.patch(
            f"/todos/{created['id']}",
            json={"description": "updated desc only"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["description"] == "updated desc only"
        assert data["priority"] == "high"  # unchanged

    async def test_update_priority_to_low(self, client):
        """PATCH with explicit priority → value.value branch (line 116) executes."""
        created = await _create(client, title="priority update", priority="medium")
        resp = await client.patch(
            f"/todos/{created['id']}",
            json={"priority": "low"},
        )
        assert resp.status_code == 200
        assert resp.json()["priority"] == "low"

    async def test_search_ilike_matching(self, client):
        """ILIKE search covers branch where search is truthy (line 81)."""
        await _create(client, title="ILiKeSeArCh special")
        resp = await client.get("/todos/?search=ilikesearch")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert any("ILiKeSeArCh" in i["title"] for i in data["items"])

    async def test_list_with_all_filters_combined(self, client):
        """All three filter branches (completed, priority, search) active at once."""
        todo = await _create(client, title="combo-filter-target", priority="high")
        await client.patch(f"/todos/{todo['id']}/toggle")
        resp = await client.get(
            "/todos/?completed=true&priority=high&search=combo-filter-target"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        item = data["items"][0]
        assert item["completed"] is True
        assert item["priority"] == "high"

    async def test_delete_covers_flush(self, client):
        """DELETE path: _get_or_404 → db.delete → MessageResponse (lines 145-146)."""
        created = await _create(client, title="flush-coverage delete")
        resp = await client.delete(f"/todos/{created['id']}")
        assert resp.status_code == 200
        body = resp.json()
        assert "deleted" in body["message"].lower()
        assert str(created["id"]) in body["message"]

    async def test_list_second_page_empty(self, client):
        """Large offset → empty items list (covers the offset branch path)."""
        resp = await client.get("/todos/?page=9999&page_size=50")
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    async def test_update_sets_completed_false(self, client):
        """PATCH completed=False on an already-false todo (setattr branch)."""
        created = await _create(client, title="set false")
        resp = await client.patch(f"/todos/{created['id']}", json={"completed": False})
        assert resp.status_code == 200
        assert resp.json()["completed"] is False

    async def test_create_with_all_optional_fields_none(self, client):
        """POST with only title — all optional fields default to None/medium."""
        resp = await client.post("/todos/", json={"title": "bare minimum"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["description"] is None
        assert data["due_date"] is None
        assert data["priority"] == "medium"
        assert data["completed"] is False


# ---------------------------------------------------------------------------
# Config coverage — cors_origins_list branch
# ---------------------------------------------------------------------------

class TestConfigCoverage:
    def test_cors_origins_list_wildcard(self):
        from app.config import Settings
        s = Settings(CORS_ORIGINS="*")
        assert s.cors_origins_list == ["*"]

    def test_cors_origins_list_multiple(self):
        from app.config import Settings
        s = Settings(CORS_ORIGINS="http://localhost:3000,https://example.com")
        result = s.cors_origins_list
        assert "http://localhost:3000" in result
        assert "https://example.com" in result
        assert len(result) == 2
