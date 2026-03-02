import re
import html
import logging

from typing import List, Tuple
from aiogram.types import User

from src.config import MAX_CAPTION
from src.utils.emoji import get_emoji, EMOJI_ERROR, EMOJI_ARROW

logger = logging.getLogger(__name__)

def get_user_link(user: User) -> str:
    """Возвращает кликабельное имя пользователя."""
    full_name = html.escape(user.full_name)
    if user.username:
        return f'<a href="https://t.me/{user.username}">{full_name}</a>'
    return f'<a href="tg://user?id={user.id}">{full_name}</a>'