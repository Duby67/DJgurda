"""
Ядро модуля базы данных.

Содержит настройки асинхронного соединения с БД и функции инициализации.
"""

import logging

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from src.config import DB_FILE
from .models.base import Base

logger = logging.getLogger(__name__)

# URL для подключения к SQLite с асинхронным драйвером
SQLALCHEMY_DATABASE_URL = f"sqlite+aiosqlite:///{DB_FILE.as_posix()}"

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
    Инициализирует базу данных: создает таблицы на основе актуальных моделей.
    """
    try:
        # Создаем все таблицы на основе моделей
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created")

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
