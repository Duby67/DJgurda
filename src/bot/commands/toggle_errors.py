import logging

from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from src.middlewares.db import get_errors_enabled, set_errors_enabled
from src.bot.processing.emoji import EMOJI_SUCCESS, EMOJI_ERROR

router = Router()
logger = logging.getLogger(__name__)

@router.message(Command("toggle_errors"))
async def toggle_errors(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    try:
        current = await get_errors_enabled(chat_id)
        new_state = not current
        await set_errors_enabled(chat_id, new_state)

        status = f"{EMOJI_SUCCESS} включена" if new_state else f"{EMOJI_ERROR} отключена"
        await message.reply(f"Отправка сообщений об ошибках в этом чате {status}.")
    except Exception as e:
        logger.exception(f"Ошибка при выполнении /toggle_errors в чате {chat_id} от пользователя {user_id}")
        await message.reply("❌ Произошла ошибка при переключении отправки ошибок.")