import logging

from sqlalchemy import select

from src.middlewares.db.core import AsyncSessionLocal
from src.middlewares.db.models.bot_settings import BotSettings

logger = logging.getLogger(__name__)

async def _get_setting(chat_id: int, column: str, default):
    try:
        async with AsyncSessionLocal() as session:
            settings = await session.get(BotSettings, chat_id)
            if settings is None:
                logger.debug(f"{column} для chat {chat_id}: запись не найдена")
                return default
            return getattr(settings, column)
    except Exception as e:
        logger.exception(f"Ошибка в _get_setting({column}) для chat {chat_id}")
        return default

async def _set_setting(chat_id: int, column: str, value: bool):
    try:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                settings = await session.get(BotSettings, chat_id)
                if settings is None:
                    settings = BotSettings(chat_id=chat_id)
                    setattr(settings, column, value)
                    session.add(settings)
                    logger.info(f"Создана запись для chat {chat_id} с {column}={value}")
                else:
                    setattr(settings, column, value)
                    logger.info(f"Обновлена {column} для chat {chat_id}: {value}")
    except Exception as e:
        logger.exception(f"Ошибка в _set_setting({column}) для chat {chat_id}")
        raise

async def get_chats_with_notifications_enabled():
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(BotSettings.chat_id).where(BotSettings.notifications_enabled == True)
            )
            return [row[0] for row in result.all()]
    except Exception as e:
        logger.exception("Ошибка получения списка чатов с уведомлениями")
        return []


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