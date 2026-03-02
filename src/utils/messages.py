import re
import html

from src.config import MAX_CAPTION
from src.utils.Emoji import emoji, EMOJI_ARROW, EMOJI_ERROR

HASHTAG_PATTERN = re.compile(r'#\w+')

def _remove_hashtags(text: str) -> str:
    cleaned = HASHTAG_PATTERN.sub('', text)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned

def build_caption(
    user_context: str,
    file_info: dict,
    user_link: str,
    url: str,
    handler
) -> str:
    source = handler.source_name
    lines = []
    
    if user_context:
        safe_context = html.escape(user_context)
        lines.append(safe_context)
        
    if file_info['type'] == 'video':
        lines.append("")
        clean_title = _remove_hashtags(file_info['title'])
        safe_title = html.escape(clean_title)
        safe_uploader = html.escape(file_info['uploader'])
        lines.append(f"🎬{safe_title} — {safe_uploader}")
        
    lines.append("")
    lines.append(f"{EMOJI_ARROW} {user_link}")
    lines.append(f"{emoji(source)} <a href='{url}'>{source}</a>")
    caption = "\n".join(lines)
    
    if len(caption) > MAX_CAPTION:
        caption = caption[:MAX_CAPTION-3] + "..."
    return caption

def build_error(
    error_message: str,
    url: str,
    handler
    ) -> str:
    source = handler.source_name
    error_text = (
        f"{EMOJI_ERROR} {error_message}.\n"
        f"{emoji(source)} <a href='{url}'>{source}</a>"
    )
    return error_text