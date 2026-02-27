import re
import html
import logging

from typing import List, Tuple
from aiogram.types import User

from src.services.base import BaseHandler
from src.config import MAX_CAPTION

logger = logging.getLogger(__name__)
URL_PATTERN = re.compile(r'https?://\S+')

def get_user_link(user: User) -> str:
    """Возвращает кликабельное имя пользователя."""
    if user.username:
        return f"@{user.username}"
    name = html.escape(user.full_name)
    return f'<a href="tg://user?id={user.id}">{name}</a>'

def split_into_blocks(text: str, service_manager) -> List[Tuple[str, str, BaseHandler]]:
    """
    Разбивает текст на блоки: для каждой найденной ссылки определяет обработчик и контекст.
    Контекстом считается вся строка, в которой найдена ссылка, с удалённой этой ссылкой.
    """
    blocks = []
    lines = text.strip().split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue
        urls = URL_PATTERN.findall(line)
        for url in urls:
            handler = service_manager.get_handler(url)
            if handler:
                context = line.replace(url, '', 1).strip()
                blocks.append((url, context, handler))
            else:
                logger.debug(f"Неизвестный тип ссылки: {url}")
    return blocks

def build_caption(
    user_context: str,
    file_info: dict,
    user_link: str,
    url: str,
    handler
) -> str:
    """Формирует подпись к медиафайлу."""
    lines = []
    if user_context:
        lines.append(html.escape(user_context))
    if handler.source_name != "Яндекс.Музыка" and file_info['type'] == 'video':
        safe_title = html.escape(file_info['title'])
        safe_uploader = html.escape(file_info['uploader'])
        lines.append("")
        lines.append(f"🎬 {safe_title} — {safe_uploader}")
    lines.append("")
    lines.append(f"От ↣ {user_link}")
    lines.append(f"<a href='{url}'>{handler.source_name}</a>")
    caption = "\n".join(lines)
    if len(caption) > MAX_CAPTION:
        caption = caption[:MAX_CAPTION-3] + "..."
    return caption

def build_error_text(
    error_message: str,
    user_context: str, 
    user_link: str, 
    url: str) -> str:
    """Сообщение об ошибке."""
    error_text = (
        f"❌{error_message}.\n\n"
        f"{user_context}\n\n"
        f"От ↣ {user_link}\n"
        f"{url}"
    )
    return error_text