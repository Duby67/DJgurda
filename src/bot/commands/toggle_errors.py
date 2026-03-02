import logging

from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from src.middlewares.db import get_errors_enabled, set_errors_enabled
from src.utils.Emoji import EMOJI_SUCCESS, EMOJI_ERROR

router = Router()
logger = logging.getLogger(__name__)

@router.message(Command("enable_errors"))
async def cmd_enable_errors(message: Message):
    await __change_errors_enabled(message, "enable_errors", True)

@router.message(Command("disable_errors"))
async def cmd_disable_errors(message: Message):
    await __change_errors_enabled(message, "disable_errors", False)

@router.message(Command("toggle_errors"))
async def cmd_toggle_errors(message: Message):
    current = await get_errors_enabled(message.chat.id)
    new_state = not current
    await __change_errors_enabled(message, "toggle_errors", new_state)

async def __change_errors_enabled(message: Message, command: str, new_state: bool):
    chat_id = message.chat.id
    user_id = message.from_user.id
    try:
        await set_errors_enabled(chat_id, new_state)
        status = f"{EMOJI_SUCCESS} включена" if new_state else f"{EMOJI_ERROR} отключена"
        await message.reply(f"Отправка сообщений об ошибках в этом чате {status}.")
    except Exception as e:
        logger.exception(f"Ошибка при выполнении /{command} в чате {chat_id} от пользователя {user_id}")
        await message.reply(f"{EMOJI_ERROR} Произошла ошибка при переключении состояния бота.")