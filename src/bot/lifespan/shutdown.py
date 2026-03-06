import logging

from aiogram import Bot, Dispatcher

from src.middlewares.db import get_chats_with_notifications_enabled, close_db
from src.config import ADMIN_ID
from src.utils.Emoji import EMOJI_WARNING

logger = logging.getLogger(__name__)


async def on_shutdown(bot: Bot, dispatcher: Dispatcher) -> None:
    """Обработчик остановки бота."""
    logger.info("Бот останавливается...")
    message_text = f"{EMOJI_WARNING} Бот выключается..."
    
    try:
        # Получение чатов для уведомлений
        chats = await get_chats_with_notifications_enabled()
        
        # Закрытие соединения с БД
        await close_db()
        
        # Уведомление администратору
        try:
            await bot.send_message(chat_id=ADMIN_ID, text=message_text)
        except Exception as exc:
            logger.error("Не удалось отправить уведомление о выключении админу: %s", exc)
        
        # Рассылка уведомлений о выключении
        for chat_id in chats:
            if chat_id == ADMIN_ID:
                continue
            try:
                await bot.send_message(chat_id=chat_id, text=message_text)
            except Exception as exc:
                logger.error("Не удалось отправить уведомление о выключении в чат %s: %s", chat_id, exc)
            
    except Exception:
        logger.exception("Ошибка при остановке бота")
        raise
