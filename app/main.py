"""Application entry point — FastAPI app factory."""
import pathlib
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import create_tables
from app.routers import api, health
from app.routers.todos import router as todos_router


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    """Run DB migrations / table creation on startup."""
    await create_tables()
    yield


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="mytodoapp05-dev — Todo API",
    description=(
        "A production-grade Todo application with full CRUD, filtering, "
        "pagination, priority levels, and due-date tracking."
    ),
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
    redirect_slashes=False,
)

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Global exception handler
# ---------------------------------------------------------------------------

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal server error occurred."},
    )

# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------

_static = pathlib.Path(__file__).parent.parent / "public"
if _static.exists():
    app.mount("/public", StaticFiles(directory=str(_static)), name="static")

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(health.router, prefix="/health", tags=["health"])
app.include_router(api.router, prefix="/api", tags=["api"])
app.include_router(todos_router, prefix="/todos", tags=["todos"])

# ---------------------------------------------------------------------------
# Root — serve SPA
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def root() -> HTMLResponse:
    html = pathlib.Path(__file__).parent.parent / "public" / "index.html"
    if html.exists():
        return HTMLResponse(content=html.read_text())
    return HTMLResponse(content="<h1>App is running</h1>")
