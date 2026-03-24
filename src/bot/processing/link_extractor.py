"""Модуль `link_extractor`."""
import re
import html

from typing import List, Tuple
from aiogram.types import User

from src.utils.url import split_trailing_url_suffix

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
    matches = list(URL_PATTERN.finditer(text))
    if not matches:
        return []

    blocks = []
    previous_end = 0

    for i, match in enumerate(matches):
        raw_url = match.group(0)
        url, trailing_suffix = split_trailing_url_suffix(raw_url)
        if not url:
            previous_end = match.end()
            continue

        context_before = text[previous_end:match.start()].strip()
        adjusted_end = match.end() - len(trailing_suffix)

        # Обрабатываем контекст после последней ссылки
        if i == len(matches) - 1:
            context_after = text[adjusted_end:].strip()
            if context_after:
                context = context_before + '\n' + context_after if context_before else context_after
            else:
                context = context_before
        else:
            context = context_before

        blocks.append((url, context))
        previous_end = adjusted_end

    return blocks
