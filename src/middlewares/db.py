import logging
import aiosqlite

from typing import List

from src.config import DB_PATH

logger = logging.getLogger(__name__)

async def init_db():
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS bot_settings (
                    chat_id INTEGER PRIMARY KEY
                )"""
            )
            await __add_column(db, "bot_settings", "bot_enabled", "INTEGER", 1)
            await __add_column(db, "bot_settings", "errors_enabled", "INTEGER", 0)
            await __add_column(db, "bot_settings", "notifications_enabled", "INTEGER", 1)
            
            await db.execute("""
                CREATE TABLE IF NOT EXISTS stats (
                    chat_id INTEGER,
                    user_id INTEGER,
                    source TEXT,
                    PRIMARY KEY (chat_id, user_id, source)
                )
            """)
            await __add_column(db, "stats", "count", "INTEGER", 0)
            
            await db.commit()
            logger.info("База данных инициализирована успешно")
    except Exception as e:
        logger.exception("Ошибка инициализации БД")
        raise
    
async def set_bot_enabled(chat_id: int, enabled: bool):
    await _set_setting(chat_id, "bot_enabled", enabled)
    
async def set_errors_enabled(chat_id: int, enabled: bool):
    await _set_setting(chat_id, "errors_enabled", enabled)
    
async def set_notifications_enabled(chat_id: int, enabled: bool):
    await _set_setting(chat_id, "notifications_enabled", enabled)


async def get_bot_enabled(chat_id: int) -> bool:
    return await _get_setting(chat_id, "bot_enabled", True)

async def get_errors_enabled(chat_id: int) -> bool:
    return await _get_setting(chat_id, "errors_enabled", False)

async def get_notifications_enabled(chat_id: int) -> bool:
    return await _get_setting(chat_id, "notifications_enabled", True)


async def update_stats(chat_id: int, user_id: int, source: str):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "UPDATE stats SET count = count + 1 WHERE chat_id = ? AND user_id = ? AND source = ?",
                (chat_id, user_id, source)
            )
            if cursor.rowcount == 0:
                await db.execute(
                    "INSERT INTO stats (chat_id, user_id, source, count) VALUES (?, ?, ?, 1)",
                    (chat_id, user_id, source)
                )
                logger.debug(f"Создана запись статистики: chat {chat_id}, user {user_id}, source {source}")
            else:
                logger.debug(f"Обновлена статистика: chat {chat_id}, user {user_id}, source {source}")
            await db.commit()
    except Exception as e:
        logger.exception(f"Ошибка обновления статистики для chat {chat_id}, user {user_id}, source {source}")

async def get_chat_stats(chat_id: int, limit: int = 10):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT user_id, source, count FROM stats WHERE chat_id = ?",
                (chat_id,)
            ) as cursor:
                rows = await cursor.fetchall()
    except Exception as e:
        logger.exception(f"Ошибка получения статистики для чата {chat_id}")
        return []
    
    user_stats = {}
    for user_id, source, count in rows:
        if user_id not in user_stats:
            user_stats[user_id] = {"total": 0, "sources": {}}
        user_stats[user_id]["total"] += count
        user_stats[user_id]["sources"][source] = count
    
    stats_list = [
        (user_id, data["total"], data["sources"])
        for user_id, data in user_stats.items()
    ]
    stats_list.sort(key=lambda x: x[1], reverse=True)
    return stats_list[:limit]


async def __add_column(db, table_name, column_name, column_type, default_value=None):
    try:
        cursor = await db.execute(f"PRAGMA table_info({table_name})")
        columns = [row[1] for row in await cursor.fetchall()]
        if column_name not in columns:
            default_clause = f"DEFAULT {default_value}" if default_value is not None else ""
            await db.execute(
                f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type} {default_clause}"
            )
            logger.info(f"Добавлена колонка {column_name} в таблицу {table_name}")
    except Exception as e:
        logger.exception(f"Ошибка при добавлении колонки {column_name}: {e}")
        raise

async def _get_setting(chat_id: int, column: str, default):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(f"SELECT {column} FROM bot_settings WHERE chat_id = ?", (chat_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return bool(row[0])
                logger.debug(f"{column} для chat {chat_id}: запись не найдена")
                return default
    except Exception as e:
        logger.exception(f"Ошибка в _get_setting({column}) для chat {chat_id}")
        return default

async def _set_setting(chat_id: int, column: str, value: bool):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                f"UPDATE bot_settings SET {column} = ? WHERE chat_id = ?",
                (int(value), chat_id)
            )
            if cursor.rowcount == 0:
                await db.execute(
                    f"INSERT INTO bot_settings (chat_id, {column}) VALUES (?, ?)",
                    (chat_id, int(value))
                )
                logger.info(f"Создана запись для chat {chat_id} с {column}={value}")
            else:
                logger.info(f"Обновлена {column} для chat {chat_id}: {value}")
            await db.commit()
    except Exception as e:
        logger.exception(f"Ошибка в _set_setting({column}) для chat {chat_id}")
        raise
    
    
async def get_chats_with_notifications_enabled() -> List[int]:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT chat_id FROM bot_settings WHERE notifications_enabled = 1"
            ) as cursor:
                rows = await cursor.fetchall()
                return [row[0] for row in rows]
    except Exception as e:
        logger.exception("Ошибка получения списка чатов с уведомлениями")
        return []