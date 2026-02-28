import aiosqlite

from src.config import DB_PATH

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bot_settings (
                chat_id INTEGER PRIMARY KEY,
                bot_enabled INTEGER DEFAULT 1,
                errors_enabled INTEGER DEFAULT 0
            )
        """)
        await db.commit()
        
async def get_bot_enabled(chat_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT bot_enabled FROM bot_settings WHERE chat_id = ?", (chat_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return bool(row[0])
            await db.execute("INSERT INTO bot_settings (chat_id, bot_enabled) VALUES (?, 1)", (chat_id,))
            await db.commit()
            return True
        
async def set_bot_enabled(chat_id: int, enabled: bool):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO bot_settings (chat_id, bot_enabled, errors_enabled)
            VALUES (?, ?, 0)
            ON CONFLICT(chat_id) DO UPDATE SET bot_enabled = excluded.bot_enabled
        """, (chat_id, int(enabled)))
        await db.commit()
        
async def get_errors_enabled(chat_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT errors_enabled FROM bot_settings WHERE chat_id = ?", (chat_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return bool(row[0])
            await db.execute("INSERT INTO bot_settings (chat_id, bot_enabled, errors_enabled) VALUES (?, 1, 0)", (chat_id,))
            await db.commit()
            return False

async def set_errors_enabled(chat_id: int, enabled: bool):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO bot_settings (chat_id, bot_enabled, errors_enabled)
            VALUES (?, 1, ?)
            ON CONFLICT(chat_id) DO UPDATE SET errors_enabled = excluded.errors_enabled
        """, (chat_id, int(enabled)))
        await db.commit()