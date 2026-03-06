"""
Система миграций базы данных.

Содержит логику для безопасного обновления схемы БД с сохранением данных.
"""

import logging
from datetime import datetime
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def migrate(session: AsyncSession) -> None:
    """
    Выполняет миграции базы данных при необходимости.
    
    Обнаруживает старую схему и переносит данные в новую структуру.
    
    Args:
        session: Асинхронная сессия БД
        
    Raises:
        Exception: При критических ошибках миграции
    """
    try:
        # Проверяем существование старой таблицы stats
        result = await session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='stats'")
        )
        
        if not result.first():
            logger.info("Таблица 'stats' не найдена, миграция не требуется.")
            return

        # Проверяем структуру таблицы stats
        pragma = await session.execute(text("PRAGMA table_info(stats)"))
        columns = [row[1] for row in pragma]
        
        # Если колонка 'source' присутствует - это старая схема
        if 'source' not in columns:
            logger.info("Таблица 'stats' уже имеет новую схему или не требует миграции.")
            return

        logger.info("Обнаружена старая схема. Запускаем миграцию...")

        # Переименовываем старую таблицу
        await session.execute(text("ALTER TABLE stats RENAME TO stats_old_temp"))
        logger.debug("Старая таблица переименована в stats_old_temp")

        # Создаем новую таблицу sources
        await session.execute(text("""
            CREATE TABLE IF NOT EXISTS sources (
                id INTEGER PRIMARY KEY,
                name TEXT UNIQUE NOT NULL
            )
        """))

        # Создаем новую таблицу stats с внешним ключом
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
        
        # Создаем индекс для оптимизации запросов
        await session.execute(text("CREATE INDEX IF NOT EXISTS ix_stats_chat_id ON stats(chat_id)"))
        logger.debug("Новые таблицы созданы")

        # Переносим данные из старой схемы в новую
        await _migrate_data(session)

        # Удаляем временную таблицу
        await session.execute(text("DROP TABLE stats_old_temp"))
        logger.info("Миграция успешно завершена, временная таблица удалена.")

        await session.commit()

    except Exception:
        logger.exception("Критическая ошибка при миграции")
        await session.rollback()
        raise


async def _migrate_data(session: AsyncSession) -> None:
    """
    Переносит данные из старой схемы в новую.
    
    Args:
        session: Асинхронная сессия БД
    """
    # Получаем уникальные источники из старой таблицы
    sources_result = await session.execute(text("SELECT DISTINCT source FROM stats_old_temp"))
    source_names = [row[0] for row in sources_result]

    # Создаем записи источников и строим маппинг
    source_map = {}
    for name in source_names:
        # Проверяем существование источника
        existing = await session.execute(
            text("SELECT id FROM sources WHERE name = :name"), {"name": name}
        )
        row = existing.first()
        
        if row:
            source_map[name] = row[0]
        else:
            # Создаем новый источник
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

    # Переносим данные статистики
    rows = await session.execute(
        text("SELECT chat_id, user_id, source, count FROM stats_old_temp")
    )
    
    now = datetime.utcnow().isoformat()
    migrated_count = 0
    
    for chat_id, user_id, source, count in rows:
        source_id = source_map.get(source)
        if not source_id:
            logger.error(f"Не найден source_id для {source}, пропускаем запись")
            continue

        # Проверяем дубликаты
        existing = await session.execute(
            text("""
                SELECT id FROM stats 
                WHERE chat_id = :chat_id AND user_id = :user_id AND source_id = :source_id
            """),
            {"chat_id": chat_id, "user_id": user_id, "source_id": source_id}
        )
        
        if existing.first():
            logger.debug(f"Запись уже существует: chat {chat_id}, user {user_id}, source {source}")
            continue

        # Вставляем новую запись
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
        migrated_count += 1

    logger.info(f"Перенесено {migrated_count} записей статистики")
