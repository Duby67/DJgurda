import logging
from aiogram import Bot, Dispatcher

from src.config import ADMIN_ID
from src.middlewares.db import get_chats_with_notifications_enabled
from src.utils.Emoji import EMOJI_WARNING

logger = logging.getLogger(__name__)

async def on_shutdown(bot: Bot, dispatcher: Dispatcher) -> None:
    logger.info("Бот останавливается...")
    message_text = f"{EMOJI_WARNING} Бот выключается..."

    chats = await get_chats_with_notifications_enabled()
    for chat_id in chats:
        if chat_id == ADMIN_ID:
            continue
        try:
            await bot.send_message(chat_id=chat_id, text=message_text)
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление о выключении в чат {chat_id}: {e}")
    try:
        await bot.send_message(chat_id=ADMIN_ID, text=message_text)
    except Exception as e:
        logger.error(f"Не удалось отправить уведомление о выключении админу: {e}")