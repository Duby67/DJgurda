import time
import logging

from aiogram import Bot
from pathlib import Path
from zoneinfo import ZoneInfo
from datetime import datetime, timezone


from src.config import ADMIN_ID, PROJECT_TEMP_DIR, MAX_AGE_SECONDS
from src.middlewares.db import get_chats_with_notifications_enabled, init_db
from src.utils.Emoji import EMOJI_SUCCESS

logger = logging.getLogger(__name__)

async def on_startup(bot: Bot) -> None:
    """Обработчик запуска бота."""
    try:
        # Инициализация базы данных
        await init_db()
        
        # Очистка устаревших временных файлов
        now = time.time()
        temp_dir = Path(PROJECT_TEMP_DIR)
        if temp_dir.exists():
            for file_path in temp_dir.glob("**/*"):
                if file_path.is_file() and (now - file_path.stat().st_mtime) > MAX_AGE_SECONDS:
                    file_path.unlink()
                    logger.debug(f"Удалён устаревший файл: {file_path}")

        # Установка времени запуска
        utc_time = datetime.now(timezone.utc)
        moscow_tz = ZoneInfo("Europe/Moscow")
        bot.start_time = utc_time.astimezone(moscow_tz)
        
        logger.info("Бот запущен")
        message_text = f"{EMOJI_SUCCESS} Бот успешно запущен и готов к работе!"

        # Уведомление администратору
        try:
            await bot.send_message(chat_id=ADMIN_ID, text=message_text)
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление о запуске админу: {e}")

        # Рассылка уведомлений
        chats = await get_chats_with_notifications_enabled()
        for chat_id in chats:
            if chat_id == ADMIN_ID:
                continue
            try:
                await bot.send_message(chat_id=chat_id, text=message_text)
            except Exception as e:
                logger.error(f"Не удалось отправить уведомление о запуске в чат {chat_id}: {e}")
            
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")
        raise