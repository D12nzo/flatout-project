"""
Конфигурация подключения к PostgreSQL (async SQLAlchemy 2.0).
"""
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.SQL_ECHO,
    future=True,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Базовый класс для всех ORM-моделей."""
    pass


async def get_db() -> AsyncIterator[AsyncSession]:
    """
    FastAPI dependency. Открывает сессию на время запроса.
    Управление транзакциями делегируется бизнес-коду (begin / commit / rollback),
    чтобы корректно работал пессимистический FOR UPDATE.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
