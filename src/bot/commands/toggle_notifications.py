"""Модуль `toggle_notifications`."""
import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from src.middlewares.db import get_notifications_enabled, set_notifications_enabled
from src.utils.Emoji import EMOJI_SUCCESS, EMOJI_ERROR

router = Router()
logger = logging.getLogger(__name__)


@router.message(Command("enable_notifications"))
async def cmd_enable_notifications(message: Message) -> None:
    """Функция `cmd_enable_notifications`."""
    await _change_notifications_enabled(message, "enable_notifications", True)


@router.message(Command("disable_notifications"))
async def cmd_disable_notifications(message: Message) -> None:
    """Функция `cmd_disable_notifications`."""
    await _change_notifications_enabled(message, "disable_notifications", False)


@router.message(Command("toggle_notifications"))
async def cmd_toggle_notifications(message: Message) -> None:
    """Функция `cmd_toggle_notifications`."""
    current = await get_notifications_enabled(message.chat.id)
    new_state = not current
    await _change_notifications_enabled(message, "toggle_notifications", new_state)


async def _change_notifications_enabled(message: Message, command: str, new_state: bool) -> None:
    """Функция `_change_notifications_enabled`."""
    chat_id = message.chat.id
    user = message.from_user
    user_id = user.id if user else 0
    try:
        await set_notifications_enabled(chat_id, new_state)
        status = f"{EMOJI_SUCCESS} включены" if new_state else f"{EMOJI_ERROR} отключены"
        await message.reply(f"Уведомления о включении/отключении бота в этом чате {status}.")
    except Exception:
        logger.exception(f"Error while executing /{command} in chat {chat_id} by user {user_id}")
        await message.reply(f"{EMOJI_ERROR} Произошла ошибка при переключении состояния бота.")
