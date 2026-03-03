import logging
from datetime import datetime
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

async def migrate(session: AsyncSession):
    try:
        # 1. Проверяем существование старой таблицы
        result = await session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='stats'")
        )
        if not result.first():
            logger.info("Таблица 'stats' не найдена, миграция не требуется.")
            return

        # 2. Проверяем структуру: есть ли колонка 'source' (признак старой схемы)
        pragma = await session.execute(text("PRAGMA table_info(stats)"))
        columns = [row[1] for row in pragma]
        if 'source' not in columns:
            logger.info("Таблица 'stats' уже имеет новую схему или не требует миграции.")
            return

        logger.info("Обнаружена старая схема. Запускаем миграцию...")

        # 3. Переименовываем старую таблицу во временную
        await session.execute(text("ALTER TABLE stats RENAME TO stats_old_temp"))
        logger.debug("Старая таблица переименована в stats_old_temp")

        # 4. Создаём новые таблицы через SQL (так как create_all уже был вызван, но не создал нужную)
        # Создаём sources
        await session.execute(text("""
            CREATE TABLE IF NOT EXISTS sources (
                id INTEGER PRIMARY KEY,
                name TEXT UNIQUE NOT NULL
            )
        """))

        # Создаём новую stats с правильной структурой
        await session.execute(text("""
            CREATE TABLE IF NOT EXISTS stats (
                id INTEGER PRIMARY KEY,
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                source_id INTEGER NOT NULL,
                count INTEGER DEFAULT 0,
                created_at TIMESTAMP,
                updated_at TIMESTAMP,
                FOREIGN KEY(source_id) REFERENCES sources(id),
                UNIQUE(chat_id, user_id, source_id)
            )
        """))
        await session.execute(text("CREATE INDEX IF NOT EXISTS ix_stats_chat_id ON stats(chat_id)"))

        logger.debug("Новые таблицы созданы")

        # 5. Собираем уникальные источники из старой таблицы
        sources_result = await session.execute(text("SELECT DISTINCT source FROM stats_old_temp"))
        source_names = [row[0] for row in sources_result]

        # 6. Заполняем sources и получаем соответствие name -> id
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

        # 7. Переносим данные
        rows = await session.execute(
            text("SELECT chat_id, user_id, source, count FROM stats_old_temp")
        )
        now = datetime.utcnow().isoformat()
        for chat_id, user_id, source, count in rows:
            source_id = source_map.get(source)
            if not source_id:
                logger.error(f"Не найден source_id для {source}, пропускаем запись")
                continue

            # Проверяем дубликаты (на случай повторного запуска)
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

        # 8. Удаляем временную таблицу (или можно оставить как резервную копию)
        await session.execute(text("DROP TABLE stats_old_temp"))
        logger.info("Миграция успешно завершена, временная таблица удалена.")

        await session.commit()

    except Exception as e:
        logger.exception("Критическая ошибка при миграции")
        await session.rollback()
        raise