"""
Tests for /health and /api/info endpoints.
"""
import pytest

pytestmark = pytest.mark.asyncio


class TestHealthEndpoint:
    async def test_health_returns_200(self, client):
        resp = await client.get("/health/")
        assert resp.status_code == 200

    async def test_health_response_shape(self, client):
        resp = await client.get("/health/")
        data = resp.json()
        assert "status" in data
        assert "database" in data
        assert "uptime" in data

    async def test_health_status_ok(self, client):
        resp = await client.get("/health/")
        data = resp.json()
        # With a working in-memory DB, status must be "ok"
        assert data["status"] == "ok"
        assert data["database"] == "ok"

    async def test_health_uptime_is_numeric(self, client):
        resp = await client.get("/health/")
        data = resp.json()
        assert isinstance(data["uptime"], (int, float))
        assert data["uptime"] >= 0


class TestApiInfoEndpoint:
    async def test_api_info_returns_200(self, client):
        resp = await client.get("/api/info")
        assert resp.status_code == 200

    async def test_api_info_shape(self, client):
        resp = await client.get("/api/info")
        data = resp.json()
        required = {"app", "version", "description", "db", "env", "docs", "redoc"}
        assert required.issubset(set(data.keys()))

    async def test_api_info_app_name(self, client):
        resp = await client.get("/api/info")
        data = resp.json()
        assert data["app"] == "mytodoapp05"

    async def test_api_info_db_status(self, client):
        resp = await client.get("/api/info")
        data = resp.json()
        assert data["db"] == "ok"

    async def test_api_info_docs_paths(self, client):
        resp = await client.get("/api/info")
        data = resp.json()
        assert data["docs"] == "/docs"
        assert data["redoc"] == "/redoc"


class TestRootEndpoint:
    async def test_root_returns_html(self, client):
        resp = await client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")
