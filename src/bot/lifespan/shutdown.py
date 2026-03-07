"""Модуль `shutdown`."""
import logging

from aiogram import Bot, Dispatcher

from src.middlewares.db import get_chats_with_notifications_enabled, close_db
from src.config import ADMIN_ID
from src.utils.Emoji import EMOJI_WARNING

logger = logging.getLogger(__name__)


async def on_shutdown(bot: Bot, dispatcher: Dispatcher) -> None:
    """Обработчик остановки бота."""
    logger.info("Bot is shutting down...")
    message_text = f"{EMOJI_WARNING} Бот выключается..."

    chats: list[int] = []
    try:
        chats = await get_chats_with_notifications_enabled()
    except Exception:
        # Даже при проблеме с БД пытаемся уведомить администратора о завершении.
        logger.exception("Failed to load notification chats during shutdown")

    # Уведомление администратору должно отправляться максимально независимо от БД.
    try:
        await bot.send_message(chat_id=ADMIN_ID, text=message_text)
    except Exception as exc:
        logger.error("Failed to send shutdown notification to admin: %s", exc)

    # Рассылка уведомлений по чатам с включенными уведомлениями.
    for chat_id in chats:
        if chat_id == ADMIN_ID:
            continue
        try:
            await bot.send_message(chat_id=chat_id, text=message_text)
        except Exception as exc:
            logger.error("Failed to send shutdown notification to chat %s: %s", chat_id, exc)

    try:
        await close_db()
    except Exception:
        logger.exception("Error while closing DB during shutdown")
