import re
import html
import logging

from typing import List, Tuple
from aiogram.types import User

from src.config import MAX_CAPTION
from src.bot.processing.emoji import get_emoji, EMOJI_ERROR, EMOJI_ARROW

logger = logging.getLogger(__name__)
URL_PATTERN = re.compile(r'https?://\S+')
HASHTAG_PATTERN = re.compile(r'#\w+')

def __remove_hashtags(text: str) -> str:
    """Удаляет хештеги из текста."""
    cleaned = HASHTAG_PATTERN.sub('', text)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned

def get_user_link(user: User) -> str:
    """Возвращает кликабельное имя пользователя."""
    full_name = html.escape(user.full_name)
    if user.username:
        return f'<a href="https://t.me/{user.username}">{full_name}</a>'
    return f'<a href="tg://user?id={user.id}">{full_name}</a>'

def split_into_blocks(text: str) -> List[Tuple[str, str]]:
    """
    Разбивает текст на блоки, где каждая ссылка получает контекст:
    - для первой ссылки — текст до неё
    - для последующих — текст между предыдущей ссылкой и текущей,
    - последняя ссылка также получает текст после себя.
    Возвращает список кортежей (url, context).
    """
    urls = URL_PATTERN.findall(text)
    if not urls:
        return []
    parts = re.split(URL_PATTERN, text)
    
    blocks = []
    for i, url in enumerate(urls):
        context_before = parts[i].strip()
        if i == len(urls) - 1:
            context_after = parts[-1].strip()
            if context_after:
                if context_before:
                    context = context_before + '\n' + context_after
                else:
                    context = context_after
            else:
                context = context_before
        else:
            context = context_before

        blocks.append((url, context))

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
    if source != "Yandex.Music" and file_info['type'] == 'video':
        clean_title = __remove_hashtags(file_info['title'])
        safe_title = html.escape(clean_title)
        safe_uploader = html.escape(file_info['uploader'])
        
        lines.append("")
        lines.append(f"🎬{safe_title} — {safe_uploader}")
    lines.append("")
    lines.append(f"{EMOJI_ARROW}{user_link}")
    lines.append(f"{get_emoji(source)}<a href='{url}'>{source}</a>")
    caption = "\n".join(lines)
    
    if len(caption) > MAX_CAPTION:
        caption = caption[:MAX_CAPTION-3] + "..."
    return caption

def build_error_text(
    error_message: str,
    url: str,
    handler
    ) -> str:
    source = handler.source_name
    error_text = (
        f"{EMOJI_ERROR}{error_message}.\n"
        f"{get_emoji(source)}<a href='{url}'>{source}</a>"
    )
    return error_text