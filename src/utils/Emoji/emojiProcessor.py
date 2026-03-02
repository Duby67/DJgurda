import logging
from .emojiData import EMOJI_DATA, DEFAULT_KEY

logger = logging.getLogger(__name__)

def _make_emoji_dict(emoji_list):
    result = {}
    for item in emoji_list:
        if len(item) == 3:
            key, emoji_char, custom_id = item
        else:
            key, emoji_char = item
            custom_id = None
        result[key] = {"emoji": emoji_char, "custom_id": custom_id}
    return result

SOURCE_EMOJI = _make_emoji_dict(EMOJI_DATA)

def _get_emoji_data(key: str) -> dict:
    return SOURCE_EMOJI.get(key, SOURCE_EMOJI[DEFAULT_KEY])

def emoji(key: str) -> str:
    data = _get_emoji_data(key)
    fallback = data["emoji"]
    custom_id = data.get("custom_id")
    if custom_id:
        return f'<tg-emoji emoji-id="{custom_id}">{fallback}</tg-emoji>'
    else:
        logger.warning(f"Не найден custom_id для ключа '{key}', используется обычный эмодзи: {fallback}")
        return fallback