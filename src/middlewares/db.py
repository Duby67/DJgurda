import logging
import aiosqlite

from src.config import DB_PATH

logger = logging.getLogger(__name__)

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

async def init_db():
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS bot_settings (
                    chat_id INTEGER PRIMARY KEY,
                )
            """)
            await __add_column(db, "bot_settings", "bot_enabled", "INTEGER", 1)
            await __add_column(db, "bot_settings", "errors_enabled", "INTEGER", 0)
            
            await db.commit()
            logger.info("База данных инициализирована успешно")
    except Exception as e:
        logger.exception("Ошибка инициализации БД")
        raise

async def get_bot_enabled(chat_id: int) -> bool:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT bot_enabled FROM bot_settings WHERE chat_id = ?", (chat_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return bool(row[0])
                logger.debug(f"get_bot_enabled для chat {chat_id}: запись не найдена")
                return True
    except Exception as e:
        logger.exception(f"Ошибка в get_bot_enabled для chat {chat_id}")
        return True

async def set_bot_enabled(chat_id: int, enabled: bool):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "UPDATE bot_settings SET bot_enabled = ? WHERE chat_id = ?",
                (int(enabled), chat_id)
            )
            if cursor.rowcount == 0:
                await db.execute(
                    "INSERT INTO bot_settings (chat_id, bot_enabled) VALUES (?, ?)",
                    (chat_id, int(enabled))
                )
                logger.info(f"Создана запись для chat {chat_id} с bot_enabled={enabled}")
            else:
                logger.info(f"Обновлена bot_enabled для chat {chat_id}: {enabled}")
            await db.commit()
    except Exception as e:
        logger.exception(f"Ошибка в set_bot_enabled для chat {chat_id}")
        raise

async def get_errors_enabled(chat_id: int) -> bool:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT errors_enabled FROM bot_settings WHERE chat_id = ?", (chat_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return bool(row[0])
                logger.debug(f"get_errors_enabled для chat {chat_id}: запись не найдена")
                return False
    except Exception as e:
        logger.exception(f"Ошибка в get_errors_enabled для chat {chat_id}")
        return False

async def set_errors_enabled(chat_id: int, enabled: bool):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "UPDATE bot_settings SET errors_enabled = ? WHERE chat_id = ?",
                (int(enabled), chat_id)
            )
            if cursor.rowcount == 0:
                await db.execute(
                    "INSERT INTO bot_settings (chat_id, errors_enabled) VALUES (?, ?)",
                    (chat_id, int(enabled))
                )
                logger.info(f"Создана запись для chat {chat_id} с errors_enabled={enabled}")
            else:
                logger.info(f"Обновлена errors_enabled для chat {chat_id}: {enabled}")
            await db.commit()
    except Exception as e:
        logger.exception(f"Ошибка в set_errors_enabled для chat {chat_id}")
        raise