import logging

from typing import Dict
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from src.bot.processing.emoji import EMOJI_ERROR, EMOJI_SUCCESS

logger = logging.getLogger(__name__)
router = Router()

_error_settings: Dict[int, bool] = {}

def is_error_messages_enabled(chat_id: int) -> bool:
    return _error_settings.get(chat_id, False)

def set_error_messages_enabled(chat_id: int, enabled: bool) -> None:
    _error_settings[chat_id] = enabled

def reset_error_settings() -> None:
    _error_settings.clear()
    
@router.message(Command("toggle_errors"))
async def toggle_errors(message: Message):
    chat_id = message.chat.id
    current = is_error_messages_enabled(chat_id)
    set_error_messages_enabled(chat_id, not current)
    status = f"{EMOJI_SUCCESS} включена" if not current else f"{EMOJI_ERROR} отключена"
    await message.reply(f"Отправка сообщений об ошибках в этом чате {status}.")