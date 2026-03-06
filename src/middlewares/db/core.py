"""
Ядро модуля базы данных.

Содержит настройки асинхронного соединения с БД и функции инициализации.
"""

import logging

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from src.config import DB_PATH
from .models.base import Base
from .migration import migrate

logger = logging.getLogger(__name__)

# URL для подключения к SQLite с асинхронным драйвером
SQLALCHEMY_DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"

# Асинхронный движок базы данных
engine = create_async_engine(
    SQLALCHEMY_DATABASE_URL,
    echo=False,  # Включить для отладки SQL-запросов
    future=True   # Использовать возможности SQLAlchemy 2.0
)

# Фабрика асинхронных сессий
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False  # Не истекать объектам после коммита
)

async def init_db() -> None:
    """
    Инициализирует базу данных: создает таблицы и применяет миграции.
    """
    try:
        # Создаем все таблицы на основе моделей
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created")

        # Применяем миграции
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await migrate(session)

        logger.info("Database initialized successfully")
        
    except Exception:
        logger.exception("Database initialization error")
        raise

async def close_db() -> None:
    """
    Корректно закрывает соединения с базой данных.
    """
    await engine.dispose()
    logger.info("Database connections closed")
