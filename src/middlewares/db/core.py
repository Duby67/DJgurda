import logging

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from src.config import DB_PATH
from .models.base import Base
from .migration import migrate

from .models import sources, stats, bot_settings

logger = logging.getLogger(__name__)

SQLALCHEMY_DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"

engine = create_async_engine(
    SQLALCHEMY_DATABASE_URL,
    echo=False,
    future=True
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        async with session.begin():
            await migrate(session)

    logger.info("База данных инициализирована успешно")

async def close_db():
    await engine.dispose()