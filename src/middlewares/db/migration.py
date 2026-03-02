import logging

from datetime import datetime
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models.sources import Source
from .models.stats import Stats

logger = logging.getLogger(__name__)

async def migrate(session: AsyncSession):
    try:
        result = await session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='stats'")
        )
        if not result.first():
            logger.info("Таблица 'stats' не найдена, миграция не требуется.")
            return

        pragma = await session.execute(text("PRAGMA table_info(stats)"))
        columns = [row[1] for row in pragma]
        if 'source' not in columns or 'source_id' in columns:
            logger.info("Таблица 'stats' уже имеет новую схему или миграция не нужна.")
            return

        logger.info("Обнаружена старая схема. Запускаем миграцию...")

        sources_result = await session.execute(text("SELECT DISTINCT source FROM stats"))
        source_names = [row[0] for row in sources_result]

        source_map = {}
        for name in source_names:
            existing = await session.execute(
                select(Source).where(Source.name == name)
            )
            source_obj = existing.scalar_one_or_none()
            if source_obj:
                source_map[name] = source_obj.id
            else:
                new_source = Source(name=name)
                session.add(new_source)
                await session.flush()
                source_map[name] = new_source.id
                logger.debug(f"Добавлен новый источник: {name}")

        rows = await session.execute(
            text("SELECT chat_id, user_id, source, count FROM stats")
        )
        for chat_id, user_id, source, count in rows:
            source_id = source_map.get(source)
            if not source_id:
                logger.error(f"Не найден source_id для {source}, пропускаем запись")
                continue

            existing_stats = await session.execute(
                select(Stats).where(
                    Stats.chat_id == chat_id,
                    Stats.user_id == user_id,
                    Stats.source_id == source_id
                )
            )
            if existing_stats.first():
                continue

            new_stats = Stats(
                chat_id=chat_id,
                user_id=user_id,
                source_id=source_id,
                count=count,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            session.add(new_stats)

        await session.execute(text("ALTER TABLE stats RENAME TO stats_backup"))
        logger.info("Миграция успешно завершена, старая таблица переименована в 'stats_backup'.")
        await session.commit()

    except Exception as e:
        logger.exception("Критическая ошибка при миграции")
        await session.rollback()
        raise