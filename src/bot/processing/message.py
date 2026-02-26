import re
import html
from typing import List, Tuple, Optional
from aiogram.types import User
from src.services.base import BaseHandler

def get_user_link(user: User) -> str:
    """Возвращает ссылку на пользователя (username или tg://)."""
    if user.username:
        return f"@{user.username}"
    name = html.escape(user.full_name)
    return f'<a href="tg://user?id={user.id}">{name}</a>'

def split_into_blocks(text: str, service_manager) -> List[Tuple[str, str, BaseHandler]]:
    """
    Разбивает текст на блоки (url + контекст).
    Каждый блок — кортеж (url, контекст, обработчик).
    """
    blocks = []
    lines = text.strip().split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Ищем первое слово, похожее на URL
        words = line.split()
        for word in words:
            if re.match(r'https?://\S+', word):
                url = word
                context = line.replace(url, '').strip()
                handler = service_manager.get_handler(url)
                if handler:
                    blocks.append((url, context, handler))
                break  # берём только первый URL в строке
    return blocks