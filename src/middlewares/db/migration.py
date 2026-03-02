import logging

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

async def migrate_from_old_schema(session: AsyncSession):
    try:
        result = await session.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='stats_old'"
        )
        if result.first():
            logger.info("Миграция уже была выполнена ранее, пропускаем.")
            return
    except Exception:
        pass