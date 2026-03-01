import logging

from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from src.middlewares.db import get_notifications_enabled, set_notifications_enabled
from src.bot.processing.emoji import EMOJI_SUCCESS, EMOJI_ERROR

router = Router()
logger = logging.getLogger(__name__)


@router.message(Command("enable_notifications"))
async def cmd_enable_notifications(message: Message):
    __change_notifications_enabled(message, "enable_notifications", True)

@router.message(Command("disable_notifications"))
async def cmd_disable_notifications(message: Message):
    __change_notifications_enabled(message, "disable_notifications", False)

@router.message(Command("toggle_notifications"))
async def cmd_toggle_notifications(message: Message):
    current = await get_notifications_enabled(message.chat_id)
    new_state = not current
    __change_notifications_enabled(message, "toggle_notifications", new_state)


async def __change_notifications_enabled(message: Message,command: str, new_state: bool):
    chat_id = message.chat.id
    user_id = message.from_user.id
    try:
        await set_notifications_enabled(chat_id, new_state)
        status = f"{EMOJI_SUCCESS} включены" if new_state else f"{EMOJI_ERROR} отключены"
        await message.reply(f"Уведомления о включении/отключении бота в этом чате {status}.")
    except Exception as e:
        logger.exception(f"Ошибка при выполнении /{command} в чате {chat_id} от пользователя {user_id}")
        await message.reply(f"{EMOJI_ERROR} Произошла ошибка при переключении состояния бота.")