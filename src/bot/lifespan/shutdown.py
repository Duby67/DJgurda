import logging
from aiogram import Bot, Dispatcher

from src.config import ADMIN_ID
logger = logging.getLogger(__name__)

async def on_shutdown(bot: Bot, dispatcher: Dispatcher) -> None:
    logger.info("Бот останавливается...")
    try:
        await bot.send_message(chat_id=ADMIN_ID, text="⚠️ Бот выключается...")
    except Exception as e:
        logger.error(f"Не удалось отправить уведомление о выключении: {e}")