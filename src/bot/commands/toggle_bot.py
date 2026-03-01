import logging

from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from src.middlewares.db import get_bot_enabled, set_bot_enabled
from src.bot.processing.emoji import EMOJI_SUCCESS, EMOJI_ERROR

router = Router()
logger = logging.getLogger(__name__)


@router.message(Command("start"))
async def cmd_start_bot(message: Message):
    __change_bot_state(message, "start", True)

@router.message(Command("stop"))
async def cmd_stop_bot(message: Message):
    __change_bot_state(message, "stop", False)

@router.message(Command("toggle_bot"))
async def cmd_toggle_bot(message: Message):
    current = await get_bot_enabled(message.chat_id)
    new_state = not current
    __change_bot_state(message, "start", new_state)


async def __change_bot_state(message: Message,command: str, new_state: bool):
    chat_id = message.chat.id
    user_id = message.from_user.id
    try:
        await set_bot_enabled(chat_id, new_state)
        status = f"{EMOJI_SUCCESS} DJgurda включён" if new_state else f"{EMOJI_ERROR} DJgurda отключён"
        await message.reply(status)
    except Exception as e:
        logger.exception(f"Ошибка при выполнении /{command} в чате {chat_id} от пользователя {user_id}")
        await message.reply(f"{EMOJI_ERROR} Произошла ошибка при переключении состояния бота.")