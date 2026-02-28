import os
import aiosqlite

from typing import Optional
from src.config import DB_PATH

async def init_db():
    """Создаёт таблицу, если её нет."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bot_settings (
                chat_id INTEGER PRIMARY KEY,
                bot_enabled INTEGER DEFAULT 1
            )
        """)
        await db.commit()
        
async def get_bot_enabled(chat_id: int) -> bool:
    """Возвращает True, если бот включён для данного чата."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT bot_enabled FROM bot_settings WHERE chat_id = ?", (chat_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return bool(row[0])
            await db.execute("INSERT INTO bot_settings (chat_id, bot_enabled) VALUES (?, 1)", (chat_id,))
            await db.commit()
            return True
        
async def set_bot_enabled(chat_id: int, enabled: bool):
    """Устанавливает состояние для чата."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO bot_settings (chat_id, bot_enabled)
            VALUES (?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET bot_enabled = excluded.bot_enabled
        """, (chat_id, int(enabled)))
        await db.commit()