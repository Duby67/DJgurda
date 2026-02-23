import re
from typing import List, Tuple

from base_handler import BaseHandler

def split_into_blocks(text: str, handlers: List[BaseHandler]) -> List[Tuple[str, str, BaseHandler]]:
    """
    Разбивает текст на блоки (url, контекст, обработчик).
    Ищет все ссылки, соответствующие любому из паттернов, и группирует их с окружающим текстом.
    Возвращает список кортежей (url, user_context, handler).
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
        before = text[prev_end:start].strip()
        if i < len(matches) - 1:
            next_start = matches[i+1][0]
            after = text[end:next_start].strip()
        else:
            after = text[end:].strip()
        # Объединяем текст до и после ссылки
        user_context = (before + " " + after).strip()
        blocks.append((url, user_context, handler))
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