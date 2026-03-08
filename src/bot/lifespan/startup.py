"""Модуль `startup`."""
import logging

from aiogram import Bot
from zoneinfo import ZoneInfo
from datetime import datetime, timezone

from src.config import ADMIN_ID, MAX_AGE_SECONDS
from src.handlers.manager import get_active_handler_names
from src.middlewares.db import get_chats_with_notifications_enabled, init_db
from src.utils.Emoji import EMOJI_SUCCESS
from src.utils.runtime_storage import cleanup_expired_temp_files, ensure_runtime_storage

logger = logging.getLogger(__name__)


async def on_startup(bot: Bot) -> None:
    """Обработчик запуска бота."""
    try:
        # Подготовка runtime-хранилища (БД + temp-папки по обработчикам).
        ensure_runtime_storage(get_active_handler_names())
        cleanup_expired_temp_files(MAX_AGE_SECONDS)

        # Инициализация базы данных
        await init_db()

        # Установка времени запуска
        utc_time = datetime.now(timezone.utc)
        moscow_tz = ZoneInfo("Europe/Moscow")
        bot.start_time = utc_time.astimezone(moscow_tz)
        
        logger.info("Bot started")
        message_text = f"{EMOJI_SUCCESS} Бот успешно запущен и готов к работе!"

        # Уведомление администратору
        try:
            await bot.send_message(chat_id=ADMIN_ID, text=message_text)
        except Exception as exc:
            logger.error("Failed to send startup notification to admin: %s", exc)

        # Рассылка уведомлений
        chats = await get_chats_with_notifications_enabled()
        for chat_id in chats:
            if chat_id == ADMIN_ID:
                continue
            try:
                await bot.send_message(chat_id=chat_id, text=message_text)
            except Exception as exc:
                logger.error("Failed to send startup notification to chat %s: %s", chat_id, exc)

    except Exception:
        logger.exception("Error during bot startup")
        raise
