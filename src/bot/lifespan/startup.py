import logging
from aiogram import Dispatcher

from zoneinfo import ZoneInfo
from datetime import datetime, timezone

from src.config import ADMIN_ID
logger = logging.getLogger(__name__)

async def on_startup(dispatcher: Dispatcher) -> None:
    utc_time = datetime.now(timezone.utc)
    moscow_tz = ZoneInfo("Europe/Moscow")
    dispatcher["start_time"] = utc_time.astimezone(moscow_tz)
    logger.info("Бот запущен")
    try:
        await dispatcher.bot.send_message(chat_id=ADMIN_ID, text="✅ Бот успешно запущен и готов к работе!")
    except Exception as e:
        logger.error(f"Не удалось отправить уведомление о запуске: {e}")