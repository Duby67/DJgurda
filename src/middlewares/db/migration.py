import logging

from datetime import datetime
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

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

        await session.execute(text("""
            CREATE TABLE IF NOT EXISTS sources (
                id INTEGER PRIMARY KEY,
                name TEXT UNIQUE NOT NULL
            )
        """))

        sources_result = await session.execute(text("SELECT DISTINCT source FROM stats"))
        source_names = [row[0] for row in sources_result]

        source_map = {}
        for name in source_names:
            existing = await session.execute(
                text("SELECT id FROM sources WHERE name = :name"), {"name": name}
            )
            row = existing.first()
            if row:
                source_map[name] = row[0]
            else:
                cursor = await session.execute(
                    text("INSERT INTO sources (name) VALUES (:name) RETURNING id"),
                    {"name": name}
                )
                row = cursor.first()
                source_id = row[0] if row else None
                if source_id is None:
                    logger.error(f"Не удалось получить ID для нового источника {name}")
                    continue
                source_map[name] = source_id
                logger.debug(f"Добавлен новый источник: {name}")

        rows = await session.execute(
            text("SELECT chat_id, user_id, source, count FROM stats")
        )
        now = datetime.utcnow().isoformat()
        for chat_id, user_id, source, count in rows:
            source_id = source_map.get(source)
            if not source_id:
                logger.error(f"Не найден source_id для {source}, пропускаем запись")
                continue

            existing = await session.execute(
                text("""
                    SELECT id FROM stats 
                    WHERE chat_id = :chat_id AND user_id = :user_id AND source_id = :source_id
                """),
                {"chat_id": chat_id, "user_id": user_id, "source_id": source_id}
            )
            if existing.first():
                continue

            await session.execute(
                text("""
                    INSERT INTO stats (chat_id, user_id, source_id, count, created_at, updated_at)
                    VALUES (:chat_id, :user_id, :source_id, :count, :created_at, :updated_at)
                """),
                {
                    "chat_id": chat_id,
                    "user_id": user_id,
                    "source_id": source_id,
                    "count": count,
                    "created_at": now,
                    "updated_at": now
                }
            )

        await session.execute(text("ALTER TABLE stats RENAME TO stats_backup"))
        logger.info("Миграция успешно завершена, старая таблица переименована в 'stats_backup'.")
        await session.commit()

    except Exception as e:
        logger.exception("Критическая ошибка при миграции")
        await session.rollback()
        raise