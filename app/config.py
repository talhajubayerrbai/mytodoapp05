import os
from pydantic_settings import BaseSettings
from pydantic import Field


def _build_database_url() -> str:
    """Assemble the database URL from individual env vars if provided, else fall back to default."""
    host = os.environ.get("DB_HOST")
    if host:
        port = os.environ.get("DB_PORT", "5432")
        name = os.environ.get("DB_NAME", "tododb")
        user = os.environ.get("DB_USER", "todouser")
        password = os.environ.get("DB_PASSWORD", "")
        return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{name}"
    return "sqlite+aiosqlite:///./todos.db"


class Settings(BaseSettings):
    # Server
    PORT: int = Field(default=8000)
    HOST: str = Field(default="0.0.0.0")
    APP_ENV: str = Field(default="development")

    # Database — assembled from individual vars at startup
    DATABASE_URL: str = Field(default_factory=_build_database_url)

    # Security
    SECRET_KEY: str = Field(default="change-me-in-production-use-a-long-random-string")

    # CORS
    CORS_ORIGINS: str = Field(default="*")

    @property
    def cors_origins_list(self) -> list[str]:
        if self.CORS_ORIGINS == "*":
            return ["*"]
        return [o.strip() for o in self.CORS_ORIGINS.split(",")]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
