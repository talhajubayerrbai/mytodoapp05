"""
Full CRUD test suite for /todos endpoints.

Covers:
  - Create (POST /todos/)
  - List with pagination (GET /todos/)
  - Filtering by completed / priority / search
  - Get single (GET /todos/{id})
  - Update partial (PATCH /todos/{id})
  - Toggle completion (PATCH /todos/{id}/toggle)
  - Delete (DELETE /todos/{id})
  - 404 handling
  - Validation errors (blank title, bad priority, etc.)
"""
import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _create(client: AsyncClient, **kwargs) -> dict:
    """Helper: POST a todo and assert 201."""
    payload = {"title": "Test todo", "priority": "medium", **kwargs}
    resp = await client.post("/todos/", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# CREATE
# ---------------------------------------------------------------------------

class TestCreateTodo:
    async def test_create_minimal(self, client):
        data = await _create(client, title="Buy milk")
        assert data["title"] == "Buy milk"
        assert data["priority"] == "medium"
        assert data["completed"] is False
        assert data["description"] is None
        assert data["due_date"] is None
        assert "id" in data
        assert "created_at" in data
        assert "updated_at" in data

    async def test_create_full(self, client):
        data = await _create(
            client,
            title="Ship feature",
            description="Deploy to prod by EOD",
            priority="high",
            due_date="2099-12-31T23:59:00Z",
        )
        assert data["title"] == "Ship feature"
        assert data["description"] == "Deploy to prod by EOD"
        assert data["priority"] == "high"
        assert data["due_date"] is not None

    async def test_create_low_priority(self, client):
        data = await _create(client, title="Low prio task", priority="low")
        assert data["priority"] == "low"

    async def test_create_strips_whitespace(self, client):
        data = await _create(client, title="  spaced title  ")
        assert data["title"] == "spaced title"

    async def test_create_blank_title_rejected(self, client):
        resp = await client.post("/todos/", json={"title": "   "})
        assert resp.status_code == 422

    async def test_create_empty_title_rejected(self, client):
        resp = await client.post("/todos/", json={"title": ""})
        assert resp.status_code == 422

    async def test_create_title_too_long(self, client):
        resp = await client.post("/todos/", json={"title": "x" * 256})
        assert resp.status_code == 422

    async def test_create_invalid_priority(self, client):
        resp = await client.post("/todos/", json={"title": "task", "priority": "urgent"})
        assert resp.status_code == 422

    async def test_create_missing_title(self, client):
        resp = await client.post("/todos/", json={"priority": "low"})
        assert resp.status_code == 422

    async def test_create_description_too_long(self, client):
        resp = await client.post("/todos/", json={"title": "ok", "description": "x" * 2001})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# LIST / PAGINATION
# ---------------------------------------------------------------------------

class TestListTodos:
    async def test_list_returns_paginated(self, client):
        # Create a few todos
        for i in range(3):
            await _create(client, title=f"List test {i}")
        resp = await client.get("/todos/")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert "pages" in data
        assert isinstance(data["items"], list)

    async def test_pagination_page_size(self, client):
        for i in range(5):
            await _create(client, title=f"Paged {i}")
        resp = await client.get("/todos/?page=1&page_size=2")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) <= 2

    async def test_pagination_invalid_page(self, client):
        resp = await client.get("/todos/?page=0")
        assert resp.status_code == 422

    async def test_pagination_page_size_too_large(self, client):
        resp = await client.get("/todos/?page_size=101")
        assert resp.status_code == 422

    async def test_filter_by_completed_false(self, client):
        await _create(client, title="Open task")
        resp = await client.get("/todos/?completed=false")
        assert resp.status_code == 200
        data = resp.json()
        assert all(not item["completed"] for item in data["items"])

    async def test_filter_by_completed_true(self, client):
        todo = await _create(client, title="Will be done")
        await client.patch(f"/todos/{todo['id']}/toggle")
        resp = await client.get("/todos/?completed=true")
        assert resp.status_code == 200
        data = resp.json()
        assert all(item["completed"] for item in data["items"])

    async def test_filter_by_priority(self, client):
        await _create(client, title="High task", priority="high")
        resp = await client.get("/todos/?priority=high")
        assert resp.status_code == 200
        data = resp.json()
        assert all(item["priority"] == "high" for item in data["items"])

    async def test_search_by_title(self, client):
        await _create(client, title="unique_search_xyz")
        resp = await client.get("/todos/?search=unique_search_xyz")
        assert resp.status_code == 200
        data = resp.json()
        assert any("unique_search_xyz" in item["title"] for item in data["items"])

    async def test_search_no_results(self, client):
        resp = await client.get("/todos/?search=zzznomatch999")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []

    async def test_search_too_long_rejected(self, client):
        resp = await client.get(f"/todos/?search={'x' * 101}")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET SINGLE
# ---------------------------------------------------------------------------

class TestGetTodo:
    async def test_get_existing(self, client):
        created = await _create(client, title="Get me")
        resp = await client.get(f"/todos/{created['id']}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == created["id"]
        assert data["title"] == "Get me"

    async def test_get_nonexistent(self, client):
        resp = await client.get("/todos/999999")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    async def test_get_invalid_id_type(self, client):
        resp = await client.get("/todos/abc")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# UPDATE (PATCH)
# ---------------------------------------------------------------------------

class TestUpdateTodo:
    async def test_update_title(self, client):
        created = await _create(client, title="Old title")
        resp = await client.patch(f"/todos/{created['id']}", json={"title": "New title"})
        assert resp.status_code == 200
        assert resp.json()["title"] == "New title"

    async def test_update_priority(self, client):
        created = await _create(client, title="Priority change")
        resp = await client.patch(f"/todos/{created['id']}", json={"priority": "high"})
        assert resp.status_code == 200
        assert resp.json()["priority"] == "high"

    async def test_update_description(self, client):
        created = await _create(client, title="Desc update")
        resp = await client.patch(f"/todos/{created['id']}", json={"description": "New desc"})
        assert resp.status_code == 200
        assert resp.json()["description"] == "New desc"

    async def test_update_completed_flag(self, client):
        created = await _create(client, title="Mark done")
        resp = await client.patch(f"/todos/{created['id']}", json={"completed": True})
        assert resp.status_code == 200
        assert resp.json()["completed"] is True

    async def test_update_due_date(self, client):
        created = await _create(client, title="Due date update")
        resp = await client.patch(
            f"/todos/{created['id']}",
            json={"due_date": "2099-06-15T10:00:00Z"},
        )
        assert resp.status_code == 200
        assert resp.json()["due_date"] is not None

    async def test_update_partial_preserves_other_fields(self, client):
        created = await _create(client, title="Preserve me", priority="high", description="keep this")
        resp = await client.patch(f"/todos/{created['id']}", json={"title": "Changed"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["priority"] == "high"
        assert data["description"] == "keep this"

    async def test_update_blank_title_rejected(self, client):
        created = await _create(client, title="Valid title")
        resp = await client.patch(f"/todos/{created['id']}", json={"title": "  "})
        assert resp.status_code == 422

    async def test_update_nonexistent(self, client):
        resp = await client.patch("/todos/999999", json={"title": "Ghost"})
        assert resp.status_code == 404

    async def test_update_invalid_priority(self, client):
        created = await _create(client, title="Bad priority update")
        resp = await client.patch(f"/todos/{created['id']}", json={"priority": "critical"})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# TOGGLE
# ---------------------------------------------------------------------------

class TestToggleTodo:
    async def test_toggle_false_to_true(self, client):
        created = await _create(client, title="Toggle me")
        assert created["completed"] is False
        resp = await client.patch(f"/todos/{created['id']}/toggle")
        assert resp.status_code == 200
        assert resp.json()["completed"] is True

    async def test_toggle_true_to_false(self, client):
        created = await _create(client, title="Toggle back")
        # Toggle on
        await client.patch(f"/todos/{created['id']}/toggle")
        # Toggle off
        resp = await client.patch(f"/todos/{created['id']}/toggle")
        assert resp.status_code == 200
        assert resp.json()["completed"] is False

    async def test_toggle_nonexistent(self, client):
        resp = await client.patch("/todos/999999/toggle")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------

class TestDeleteTodo:
    async def test_delete_existing(self, client):
        created = await _create(client, title="Delete me")
        resp = await client.delete(f"/todos/{created['id']}")
        assert resp.status_code == 200
        assert "deleted" in resp.json()["message"].lower()

    async def test_delete_then_get_404(self, client):
        created = await _create(client, title="Gone soon")
        await client.delete(f"/todos/{created['id']}")
        resp = await client.get(f"/todos/{created['id']}")
        assert resp.status_code == 404

    async def test_delete_nonexistent(self, client):
        resp = await client.delete("/todos/999999")
        assert resp.status_code == 404

    async def test_double_delete(self, client):
        created = await _create(client, title="Double delete")
        await client.delete(f"/todos/{created['id']}")
        resp = await client.delete(f"/todos/{created['id']}")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# RESPONSE SHAPE
# ---------------------------------------------------------------------------

class TestResponseShape:
    async def test_response_has_all_fields(self, client):
        created = await _create(
            client,
            title="Shape check",
            description="desc here",
            priority="low",
            due_date="2099-01-01T00:00:00Z",
        )
        required_fields = {"id", "title", "description", "priority",
                           "completed", "due_date", "created_at", "updated_at"}
        assert required_fields.issubset(set(created.keys()))

    async def test_list_response_shape(self, client):
        resp = await client.get("/todos/?page_size=1")
        assert resp.status_code == 200
        data = resp.json()
        required = {"items", "total", "page", "page_size", "pages"}
        assert required.issubset(set(data.keys()))
        assert isinstance(data["items"], list)
        assert isinstance(data["total"], int)
        assert isinstance(data["pages"], int)
