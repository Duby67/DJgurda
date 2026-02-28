import re
from src.config import SOURCE_EMOJI, DEFAULT_KEY

def __get_emoji_data(key: str) -> dict:
    """Возвращает запись из словаря эмодзи по ключу"""
    return SOURCE_EMOJI.get(key, SOURCE_EMOJI[DEFAULT_KEY])

def __get_emoji_text(source: dict) -> str:
    """Извлекает обычный эмодзи из записи"""
    return source["emoji"]

def __get_emoji_custom_id(source: dict) -> str:
    """Извлекает custom_id из записи"""
    return source.get("custom_id")

def get_emoji(key: str) -> str:
    data = __get_emoji_data(key)
    fallback = __get_emoji_text(data)
    custom_id = __get_emoji_custom_id(data)
    if custom_id:
        return f'<tg-emoji emoji-id="{custom_id}">{fallback}</tg-emoji>'
    return fallback

EMOJI_DJGURDA = get_emoji("DJgurda")
EMOJI_VERSION = get_emoji("Version")
EMOJI_STARTTIME = get_emoji("StartTime")

EMOJI_ERROR = get_emoji("ERROR")
EMOJI_WARNING = get_emoji("WARNING")
EMOJI_SUCCESS = get_emoji("SUCCESS")

EMOJI_ARROW = get_emoji("Arrow")
EMOJI_TIKTOK = get_emoji("TikTok")
EMOJI_YOUTUBE = get_emoji("YouTube")
EMOJI_INSTAGRAM = get_emoji("Instagram")
EMOJI_YANDEXMUSIC = get_emoji("Yandex.Music")

__all__ = [
    get_emoji,
    
    "EMOJI_DJGURDA", 
    "EMOJI_VERSION", 
    "EMOJI_STARTTIME",
    
    "EMOJI_ERROR", 
    "EMOJI_WARNING", 
    "EMOJI_SUCCESS",
    
    "EMOJI_ARROW", 
    "EMOJI_TIKTOK", 
    "EMOJI_YOUTUBE",
    "EMOJI_INSTAGRAM", 
    "EMOJI_YANDEXMUSIC"
]