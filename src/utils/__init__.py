"""
Вспомогательные утилиты для бота.

Содержит функции для работы с сообщениями, URL, логированием и эмодзи.
"""

from .logger import setup_logging
from .messages import build_caption, build_error
from .url import resolve_url
from .Emoji import (
    emoji, 
    EMOJI_ERROR, 
    EMOJI_SUCCESS, 
    EMOJI_WARNING,
    EMOJI_DJGURDA,
    EMOJI_VERSION,
    EMOJI_STARTTIME,
    EMOJI_STATISTICS,
    EMOJI_FIRSTPLACE,
    EMOJI_SECONDPLACE,
    EMOJI_THIRDPLACE,
    EMOJI_VIDEO,
    EMOJI_ARROW,
    EMOJI_TIKTOK,
    EMOJI_YOUTUBE,
    EMOJI_INSTAGRAM,
    EMOJI_YANDEXMUSIC,
    EMOJI_LINK
)

__all__ = [
    # Логирование
    'setup_logging',
    
    # Сообщения
    'build_caption',
    'build_error',
    
    # URL
    'resolve_url',
    
    # Эмодзи
    'emoji',
    'EMOJI_ERROR',
    'EMOJI_SUCCESS', 
    'EMOJI_WARNING',
    'EMOJI_DJGURDA',
    'EMOJI_VERSION',
    'EMOJI_STARTTIME',
    'EMOJI_STATISTICS',
    'EMOJI_FIRSTPLACE',
    'EMOJI_SECONDPLACE', 
    'EMOJI_THIRDPLACE',
    'EMOJI_VIDEO',
    'EMOJI_ARROW',
    'EMOJI_TIKTOK',
    'EMOJI_YOUTUBE',
    'EMOJI_INSTAGRAM',
    'EMOJI_YANDEXMUSIC',
    'EMOJI_LINK'
]
