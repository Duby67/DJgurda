"""Модуль `toggle_errors`."""
import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from src.middlewares.db import get_errors_enabled, set_errors_enabled
from src.utils.Emoji import EMOJI_SUCCESS, EMOJI_ERROR

router = Router()
logger = logging.getLogger(__name__)


@router.message(Command("enable_errors"))
async def cmd_enable_errors(message: Message) -> None:
    """Функция `cmd_enable_errors`."""
    await _change_errors_enabled(message, "enable_errors", True)


@router.message(Command("disable_errors"))
async def cmd_disable_errors(message: Message) -> None:
    """Функция `cmd_disable_errors`."""
    await _change_errors_enabled(message, "disable_errors", False)


@router.message(Command("toggle_errors"))
async def cmd_toggle_errors(message: Message) -> None:
    """Функция `cmd_toggle_errors`."""
    current = await get_errors_enabled(message.chat.id)
    new_state = not current
    await _change_errors_enabled(message, "toggle_errors", new_state)


async def _change_errors_enabled(message: Message, command: str, new_state: bool) -> None:
    """Функция `_change_errors_enabled`."""
    chat_id = message.chat.id
    user = message.from_user
    user_id = user.id if user else 0
    try:
        await set_errors_enabled(chat_id, new_state)
        status = f"{EMOJI_SUCCESS} включена" if new_state else f"{EMOJI_ERROR} отключена"
        await message.reply(f"Отправка сообщений об ошибках в этом чате {status}.")
    except Exception:
        logger.exception(f"Error while executing /{command} in chat {chat_id} by user {user_id}")
        await message.reply(f"{EMOJI_ERROR} Произошла ошибка при переключении состояния бота.")
