перенести в утилс

import re
import html
import logging

from typing import List, Tuple
from aiogram.types import User

from src.config import MAX_CAPTION
from src.utils.emojiPack import get_emoji, EMOJI_ERROR, EMOJI_ARROW

logger = logging.getLogger(__name__)

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