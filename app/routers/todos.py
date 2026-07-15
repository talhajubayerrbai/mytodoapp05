"""Todo CRUD router."""
from typing import Optional
import math

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Priority, Todo
from app.schemas import MessageResponse, PaginatedTodos, TodoCreate, TodoResponse, TodoUpdate

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_or_404(todo_id: int, db: AsyncSession) -> Todo:
    result = await db.get(Todo, todo_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Todo {todo_id} not found")
    return result


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post(
    "/",
    response_model=TodoResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new todo",
)
async def create_todo(payload: TodoCreate, db: AsyncSession = Depends(get_db)) -> TodoResponse:
    todo = Todo(
        title=payload.title,
        description=payload.description,
        priority=payload.priority.value,
        due_date=payload.due_date,
    )
    db.add(todo)
    await db.flush()
    await db.refresh(todo)
    return TodoResponse.model_validate(todo)


@router.get(
    "/",
    response_model=PaginatedTodos,
    summary="List todos with optional filtering and pagination",
)
async def list_todos(
    completed: Optional[bool] = Query(None, description="Filter by completion status"),
    priority: Optional[Priority] = Query(None, description="Filter by priority"),
    search: Optional[str] = Query(None, max_length=100, description="Search in title"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
) -> PaginatedTodos:
    stmt = select(Todo)
    count_stmt = select(func.count()).select_from(Todo)

    if completed is not None:
        stmt = stmt.where(Todo.completed == completed)
        count_stmt = count_stmt.where(Todo.completed == completed)

    if priority is not None:
        stmt = stmt.where(Todo.priority == priority.value)
        count_stmt = count_stmt.where(Todo.priority == priority.value)

    if search:
        like = f"%{search}%"
        stmt = stmt.where(Todo.title.ilike(like))
        count_stmt = count_stmt.where(Todo.title.ilike(like))

    total = (await db.execute(count_stmt)).scalar_one()

    stmt = stmt.order_by(Todo.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(stmt)).scalars().all()

    return PaginatedTodos(
        items=[TodoResponse.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
        pages=max(1, math.ceil(total / page_size)),
    )


@router.get(
    "/{todo_id}",
    response_model=TodoResponse,
    summary="Get a single todo by ID",
)
async def get_todo(todo_id: int, db: AsyncSession = Depends(get_db)) -> TodoResponse:
    todo = await _get_or_404(todo_id, db)
    return TodoResponse.model_validate(todo)


@router.patch(
    "/{todo_id}",
    response_model=TodoResponse,
    summary="Update a todo (partial)",
)
async def update_todo(
    todo_id: int, payload: TodoUpdate, db: AsyncSession = Depends(get_db)
) -> TodoResponse:
    todo = await _get_or_404(todo_id, db)

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "priority" and value is not None:
            value = value.value  # store enum value string
        setattr(todo, field, value)

    await db.flush()
    await db.refresh(todo)
    return TodoResponse.model_validate(todo)


@router.patch(
    "/{todo_id}/toggle",
    response_model=TodoResponse,
    summary="Toggle todo completion status",
)
async def toggle_todo(todo_id: int, db: AsyncSession = Depends(get_db)) -> TodoResponse:
    todo = await _get_or_404(todo_id, db)
    todo.completed = not todo.completed  # type: ignore[assignment]
    await db.flush()
    await db.refresh(todo)
    return TodoResponse.model_validate(todo)


@router.delete(
    "/{todo_id}",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Delete a todo",
)
async def delete_todo(todo_id: int, db: AsyncSession = Depends(get_db)) -> MessageResponse:
    todo = await _get_or_404(todo_id, db)
    await db.delete(todo)
    return MessageResponse(message=f"Todo {todo_id} deleted successfully")
