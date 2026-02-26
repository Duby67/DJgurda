import logging
from aiogram import Dispatcher

from src.config import ADMIN_ID
logger = logging.getLogger(__name__)

async def on_shutdown(dispatcher: Dispatcher) -> None:
    logger.info("Бот останавливается...")
    try:
        await dispatcher.bot.send_message(chat_id=ADMIN_ID, text="⚠️ Бот выключается...")
    except Exception as e:
        logger.error(f"Не удалось отправить уведомление о выключении: {e}")