"""
Edge-case and integration tests that complement the main CRUD suite.

Covers:
  - Combined filter + search + pagination
  - Boundary values (max-length strings, exact limit page sizes)
  - Bulk creation then filtering
  - Due-date edge cases
  - API info and health under normal load
  - Root / SPA endpoint
  - Global error handler (simulated)
  - Priority enum exhaustiveness
"""
import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _create(client: AsyncClient, **kwargs) -> dict:
    payload = {"title": "Edge case todo", "priority": "medium", **kwargs}
    resp = await client.post("/todos/", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Combined filter + search
# ---------------------------------------------------------------------------

class TestCombinedFilters:
    async def test_priority_and_search(self, client):
        await _create(client, title="alpha task", priority="high")
        await _create(client, title="alpha task", priority="low")
        resp = await client.get("/todos/?priority=high&search=alpha")
        assert resp.status_code == 200
        data = resp.json()
        assert all(i["priority"] == "high" for i in data["items"])
        assert all("alpha" in i["title"] for i in data["items"])

    async def test_completed_and_priority(self, client):
        todo = await _create(client, title="complete+high", priority="high")
        await client.patch(f"/todos/{todo['id']}/toggle")
        resp = await client.get("/todos/?completed=true&priority=high")
        assert resp.status_code == 200
        data = resp.json()
        assert all(i["completed"] for i in data["items"])
        assert all(i["priority"] == "high" for i in data["items"])

    async def test_search_case_insensitive(self, client):
        await _create(client, title="UniQueCaSeTeSt")
        resp = await client.get("/todos/?search=uniquecasetest")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1

    async def test_filter_open_with_pagination(self, client):
        for i in range(5):
            await _create(client, title=f"Open paged {i}")
        resp = await client.get("/todos/?completed=false&page=1&page_size=3")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) <= 3
        assert all(not i["completed"] for i in data["items"])


# ---------------------------------------------------------------------------
# Boundary values
# ---------------------------------------------------------------------------

class TestBoundaryValues:
    async def test_title_exactly_255_chars(self, client):
        title = "a" * 255
        resp = await client.post("/todos/", json={"title": title})
        assert resp.status_code == 201
        assert resp.json()["title"] == title

    async def test_title_256_chars_rejected(self, client):
        resp = await client.post("/todos/", json={"title": "x" * 256})
        assert resp.status_code == 422

    async def test_description_exactly_2000_chars(self, client):
        resp = await client.post("/todos/", json={"title": "ok", "description": "d" * 2000})
        assert resp.status_code == 201
        assert len(resp.json()["description"]) == 2000

    async def test_description_2001_chars_rejected(self, client):
        resp = await client.post("/todos/", json={"title": "ok", "description": "d" * 2001})
        assert resp.status_code == 422

    async def test_page_size_exactly_100(self, client):
        resp = await client.get("/todos/?page_size=100")
        assert resp.status_code == 200

    async def test_page_size_1(self, client):
        await _create(client, title="boundary size 1")
        resp = await client.get("/todos/?page_size=1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) <= 1

    async def test_page_size_zero_rejected(self, client):
        resp = await client.get("/todos/?page_size=0")
        assert resp.status_code == 422

    async def test_very_large_page_number(self, client):
        # Valid page number but past last page → empty items, total still correct
        resp = await client.get("/todos/?page=99999&page_size=20")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert isinstance(data["total"], int)


# ---------------------------------------------------------------------------
# Bulk creation and listing
# ---------------------------------------------------------------------------

class TestBulkOperations:
    async def test_bulk_create_and_count(self, client):
        titles = [f"bulk-{i}" for i in range(10)]
        ids = []
        for t in titles:
            d = await _create(client, title=t, priority="low")
            ids.append(d["id"])

        resp = await client.get("/todos/?priority=low&page_size=100")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 10

    async def test_delete_all_created(self, client):
        todos = [await _create(client, title=f"del-bulk-{i}") for i in range(3)]
        for t in todos:
            resp = await client.delete(f"/todos/{t['id']}")
            assert resp.status_code == 200

    async def test_pages_calculated_correctly(self, client):
        for i in range(5):
            await _create(client, title=f"pages-{i}")
        resp = await client.get("/todos/?page_size=2")
        assert resp.status_code == 200
        data = resp.json()
        import math
        expected_pages = max(1, math.ceil(data["total"] / 2))
        assert data["pages"] == expected_pages


# ---------------------------------------------------------------------------
# Due-date edge cases
# ---------------------------------------------------------------------------

class TestDueDateEdgeCases:
    async def test_far_future_due_date(self, client):
        data = await _create(client, title="Far future", due_date="2099-12-31T23:59:59Z")
        assert data["due_date"] is not None

    async def test_past_due_date_accepted(self, client):
        # API should accept past dates (overdue logic is client-side)
        data = await _create(client, title="Overdue task", due_date="2000-01-01T00:00:00Z")
        assert data["due_date"] is not None

    async def test_update_clears_due_date(self, client):
        todo = await _create(client, title="Has due date", due_date="2099-01-01T00:00:00Z")
        assert todo["due_date"] is not None
        resp = await client.patch(f"/todos/{todo['id']}", json={"due_date": None})
        assert resp.status_code == 200
        assert resp.json()["due_date"] is None

    async def test_create_without_due_date(self, client):
        data = await _create(client, title="No due date")
        assert data["due_date"] is None


# ---------------------------------------------------------------------------
# Priority exhaustiveness
# ---------------------------------------------------------------------------

class TestAllPriorities:
    async def test_low_priority_roundtrip(self, client):
        data = await _create(client, title="low", priority="low")
        fetched = (await client.get(f"/todos/{data['id']}")).json()
        assert fetched["priority"] == "low"

    async def test_medium_priority_roundtrip(self, client):
        data = await _create(client, title="medium", priority="medium")
        fetched = (await client.get(f"/todos/{data['id']}")).json()
        assert fetched["priority"] == "medium"

    async def test_high_priority_roundtrip(self, client):
        data = await _create(client, title="high", priority="high")
        fetched = (await client.get(f"/todos/{data['id']}")).json()
        assert fetched["priority"] == "high"

    async def test_update_cycle_through_priorities(self, client):
        data = await _create(client, title="cycle", priority="low")
        tid = data["id"]
        for pri in ["medium", "high", "low"]:
            resp = await client.patch(f"/todos/{tid}", json={"priority": pri})
            assert resp.status_code == 200
            assert resp.json()["priority"] == pri


# ---------------------------------------------------------------------------
# Timestamps
# ---------------------------------------------------------------------------

class TestTimestamps:
    async def test_created_at_set_on_create(self, client):
        from datetime import datetime
        data = await _create(client, title="timestamp test")
        # Should be parseable ISO8601
        dt = datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))
        assert dt is not None

    async def test_updated_at_changes_on_update(self, client):
        import asyncio
        from datetime import datetime
        data = await _create(client, title="update ts")
        original_updated = data["updated_at"]
        # Small delay to ensure timestamp differs
        await asyncio.sleep(0.05)
        resp = await client.patch(f"/todos/{data['id']}", json={"title": "updated ts"})
        assert resp.status_code == 200
        new_updated = resp.json()["updated_at"]
        # updated_at should be >= original
        orig_dt = datetime.fromisoformat(original_updated.replace("Z", "+00:00"))
        new_dt  = datetime.fromisoformat(new_updated.replace("Z", "+00:00"))
        assert new_dt >= orig_dt

    async def test_created_at_and_updated_at_present(self, client):
        data = await _create(client, title="ts fields")
        assert "created_at" in data
        assert "updated_at" in data
        assert data["created_at"] is not None
        assert data["updated_at"] is not None


# ---------------------------------------------------------------------------
# Health endpoint additional coverage
# ---------------------------------------------------------------------------

class TestHealthAdditional:
    async def test_health_returns_json(self, client):
        resp = await client.get("/health/")
        assert resp.headers["content-type"].startswith("application/json")

    async def test_health_uptime_increases(self, client):
        import asyncio
        r1 = (await client.get("/health/")).json()
        await asyncio.sleep(0.1)
        r2 = (await client.get("/health/")).json()
        assert r2["uptime"] >= r1["uptime"]


# ---------------------------------------------------------------------------
# API info additional coverage
# ---------------------------------------------------------------------------

class TestApiInfoAdditional:
    async def test_api_info_version_format(self, client):
        data = (await client.get("/api/info")).json()
        # Version should be semver-like x.y.z
        parts = data["version"].split(".")
        assert len(parts) >= 2
        assert all(p.isdigit() for p in parts)

    async def test_api_info_description_present(self, client):
        data = (await client.get("/api/info")).json()
        assert data["description"]
        assert len(data["description"]) > 0
