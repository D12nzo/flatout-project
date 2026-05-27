"""
Централизованная конфигурация приложения.
Все значения берутся из переменных окружения / .env.
"""
from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:12345@localhost:5432/barbershop_db"
    )

    # App
    APP_ENV: str = "development"
    APP_NAME: str = "FlatOut API"
    APP_VERSION: str = "1.0.0"

    # Auth
    SECRET_KEY: str = Field(default="change-me-in-production")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24h

    # SQL echo (отключаем в продакшене)
    SQL_ECHO: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
