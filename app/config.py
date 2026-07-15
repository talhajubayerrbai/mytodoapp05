import os
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # Server
    PORT: int = Field(default=8000)
    HOST: str = Field(default="0.0.0.0")
    APP_ENV: str = Field(default="development")

    # Database
    DATABASE_URL: str = Field(default="sqlite+aiosqlite:///./todos.db")

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
