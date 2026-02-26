import time
import logging

from aiogram import Dispatcher
from zoneinfo import ZoneInfo
from datetime import datetime, timezone

from src.config import ADMIN_ID, PROJECT_TEMP_DIR, MAX_AGE_SECONDS
logger = logging.getLogger(__name__)

async def on_startup(dispatcher: Dispatcher) -> None:
    now = time.time()
    for f in PROJECT_TEMP_DIR.glob("**/*"):
        if f.is_file() and (now - f.stat().st_mtime) > MAX_AGE_SECONDS:
            f.unlink()

    utc_time = datetime.now(timezone.utc)
    moscow_tz = ZoneInfo("Europe/Moscow")
    dispatcher.bot["start_time"] = utc_time.astimezone(moscow_tz)
    logger.info("Бот запущен")
    try:
        await dispatcher.bot.send_message(chat_id=ADMIN_ID, text="✅ Бот успешно запущен и готов к работе!")
    except Exception as e:
        logger.error(f"Не удалось отправить уведомление о запуске: {e}")