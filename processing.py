import re
from typing import List, Tuple

from base_handler import BaseHandler

def split_into_blocks(text: str, handlers: List[BaseHandler]) -> List[Tuple[str, str, BaseHandler]]:
    """
    Разбивает текст на блоки (url, контекст, обработчик).
    Контекст для каждой ссылки — это текст, относящийся именно к ней:
      - Для первой ссылки: текст от начала до её позиции.
      - Для промежуточных ссылок: текст между предыдущей и текущей ссылкой.
      - Для последней ссылки: текст после неё до конца сообщения.
    Все пробелы и переносы сохраняются (без лишней обрезки).
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
        if i == 0:
            # Первая ссылка: контекст от начала до неё
            context = text[:start]
        else:
            # Промежуточная ссылка: контекст между предыдущей ссылкой и текущей
            context = text[prev_end:start]

        if i == len(matches) - 1:
            # Последняя ссылка: добавляем текст после неё (если он есть)
            after = text[end:]
            context = context + after  # контекст для последней = текст до + текст после
        else:
            # Для не последних ссылок текст после них не включается
            pass

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