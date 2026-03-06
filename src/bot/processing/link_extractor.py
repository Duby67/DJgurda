import re
import html

from typing import List, Tuple
from aiogram.types import User

URL_PATTERN = re.compile(r'https?://\S+')

def get_user_link(user: User) -> str:
    """
    Генерирует HTML-ссылку на пользователя.
    
    Аргументы:
        user: Объект пользователя Telegram
        
    Возвращает:
        HTML-строка с ссылкой на пользователя
    """
    full_name = html.escape(user.full_name)
    if user.username:
        return f'<a href="https://t.me/{user.username}">{full_name}</a>'
    return f'<a href="tg://user?id={user.id}">{full_name}</a>'

def split_into_blocks(text: str) -> List[Tuple[str, str]]:
    """
    Разбивает текст на блоки (URL + контекст).
    
    Аргументы:
        text: Текст сообщения с URL
        
    Возвращает:
        Список кортежей (url, context)
    """
    urls = URL_PATTERN.findall(text)
    if not urls:
        return []
    
    parts = re.split(URL_PATTERN, text)
    blocks = []
    
    for i, url in enumerate(urls):
        context_before = parts[i].strip()
        
        # Обрабатываем контекст после последней ссылки
        if i == len(urls) - 1:
            context_after = parts[-1].strip()
            if context_after:
                context = context_before + '\n' + context_after if context_before else context_after
            else:
                context = context_before
        else:
            context = context_before

        blocks.append((url, context))
    
    return blocks
