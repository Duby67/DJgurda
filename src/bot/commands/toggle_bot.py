import logging

from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from src.middlewares.db import get_bot_enabled, set_bot_enabled
from src.bot.processing.emoji import EMOJI_SUCCESS, EMOJI_ERROR

router = Router()
logger = logging.getLogger(__name__)

@router.message(Command("toggle_bot"))
async def cmd_toggle_bot(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    try:
        current = await get_bot_enabled(chat_id)
        new_state = not current
        await set_bot_enabled(chat_id, new_state)

        status = f"{EMOJI_SUCCESS} DJgurda включён" if new_state else f"{EMOJI_ERROR} DJgurda отключён"
        await message.reply(f"{status}.")
    except Exception as e:
        logger.exception(f"Ошибка при выполнении /toggle_bot в чате {chat_id} от пользователя {user_id}")
        await message.reply("❌ Произошла ошибка при переключении состояния бота.")