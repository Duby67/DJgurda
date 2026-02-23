import re
from typing import List, Tuple

from base_handler import BaseHandler

def split_into_blocks(text: str, handlers: List[BaseHandler]) -> List[Tuple[str, str, BaseHandler]]:
    """
    Разбивает текст на блоки (url, контекст, обработчик).
    Каждая ссылка получает контекст - текст от предыдущей ссылки (или начала) до текущей ссылки.
    Текст после последней ссылки добавляется к контексту последней ссылки.
    """
    matches = []
    for handler in handlers:
        for match in handler.pattern.finditer(text):
            matches.append((match.start(), match.end(), match.group(), handler))

    if not matches:
        return []

    # Сортируем по позиции в тексте
    matches.sort(key=lambda x: x[0])

    blocks = []
    prev_end = 0
    for i, (start, end, url, handler) in enumerate(matches):
        # Контекст - текст от предыдущего конца до начала текущей ссылки
        context = text[prev_end:start].strip()
        
        # Если это последняя ссылка, добавляем текст после неё
        if i == len(matches) - 1:
            after = text[end:].strip()
            if after:
                context = (context + " " + after).strip() if context else after
        
        blocks.append((url, context, handler))
        prev_end = end

    return blocks

def get_user_link(user) -> str:
    """
    Возвращает HTML-ссылку на профиль пользователя.
    Если у пользователя нет username, возвращает просто имя.
    """
    name = user.full_name
    if user.username:
        return f'<a href="https://t.me/{user.username}">{name}</a>'
    return name