from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from src.bot.processing.emoji import EMOJI_SUCCESS, EMOJI_ERROR
from src.middlewares.db import get_errors_enabled, set_errors_enabled

router = Router()

@router.message(Command("toggle_errors"))
async def toggle_errors(message: Message):
    chat_id = message.chat.id
    current = await get_errors_enabled(chat_id)
    new_state = not current
    await set_errors_enabled(chat_id, new_state)

    status = f"{EMOJI_SUCCESS} включена" if new_state else f"{EMOJI_ERROR} отключена"
    await message.reply(f"Отправка сообщений об ошибках в этом чате {status}.")