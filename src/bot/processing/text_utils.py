import re
import html
import logging

from typing import List, Tuple
from aiogram.types import User

from src.services.base import BaseHandler
from src.config import MAX_CAPTION

SOURCE_EMOJI = {
    "DJgurda": {"emoji": "🤖", "custom_id": 5264975008282742838},
    "TikTok": {"emoji": "🎵", "custom_id": 5262660471881765089},
    "YouTube": {"emoji": "📹", "custom_id": 5263003845927147424},
    "Instagram": {"emoji": "📸", "custom_id": 5264912443494144118},
    "Яндекс.Музыка": {"emoji": "🎧", "custom_id": 5264990513114683176}
}
ERROR_EMOJI = "❌"
DEFAULT_EMOJI = "🔗"

logger = logging.getLogger(__name__)
URL_PATTERN = re.compile(r'https?://\S+')
HASHTAG_PATTERN = re.compile(r'#\w+')

def get_source_emoji(source_name: str) -> str:
    """Возвращает HTML-код для отображения эмодзи источника (обычного или кастомного)."""
    info = SOURCE_EMOJI.get(source_name, {"emoji": DEFAULT_EMOJI})
    fallback = info["emoji"]
    custom_id = info.get("custom_id")
    if custom_id:
        return f'<tg-emoji emoji-id="{custom_id}">{fallback}</tg-emoji>'
    return fallback

def remove_hashtags(text: str) -> str:
    """Удаляет хештеги из текста."""
    cleaned = HASHTAG_PATTERN.sub('', text)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned

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
    source = handler.source_name
    
    if user_context:
        lines.append(html.escape(user_context))
    if source != "Яндекс.Музыка" and file_info['type'] == 'video':
        clean_title = remove_hashtags(file_info['title'])
        safe_title = html.escape(clean_title)
        safe_uploader = html.escape(file_info['uploader'])
        lines.append("")
        lines.append(f"🎬{safe_title} — {safe_uploader}")
    lines.append("")
    lines.append(f"От ↣ {user_link}")
    lines.append(f"{get_source_emoji(source)} <a href='{url}'>{source}</a>")
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
        f"{ERROR_EMOJI}{error_message}.\n\n"
        f"{user_context}\n\n"
        f"От ↣ {user_link}\n"
        f"{url}"
    )
    return error_text