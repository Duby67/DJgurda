import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from src.middlewares.db import get_bot_enabled, set_bot_enabled
from src.utils.Emoji import EMOJI_SUCCESS, EMOJI_ERROR

router = Router()
logger = logging.getLogger(__name__)


@router.message(Command("start"))
async def cmd_start_bot(message: Message) -> None:
    await _change_bot_state(message, "start", True)


@router.message(Command("stop"))
async def cmd_stop_bot(message: Message) -> None:
    await _change_bot_state(message, "stop", False)


@router.message(Command("toggle_bot"))
async def cmd_toggle_bot(message: Message) -> None:
    current = await get_bot_enabled(message.chat.id)
    new_state = not current
    await _change_bot_state(message, "toggle_bot", new_state)


async def _change_bot_state(message: Message, command: str, new_state: bool) -> None:
    chat_id = message.chat.id
    user = message.from_user
    user_id = user.id if user else 0
    try:
        await set_bot_enabled(chat_id, new_state)
        status = f"{EMOJI_SUCCESS} DJgurda включён" if new_state else f"{EMOJI_ERROR} DJgurda отключён"
        await message.reply(status)
    except Exception:
        logger.exception(f"Error while executing /{command} in chat {chat_id} by user {user_id}")
        await message.reply(f"{EMOJI_ERROR} Произошла ошибка при переключении состояния бота.")
