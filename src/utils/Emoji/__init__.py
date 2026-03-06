"""
Модуль эмодзи для бота DJgurda.

Предоставляет константы и функции для единообразного использования эмодзи
в сообщениях бота с поддержкой кастомных Telegram Emoji ID.
"""

from .emojiProcessor import emoji

# Системные эмодзи
EMOJI_DJGURDA = emoji("DJgurda")
EMOJI_VERSION = emoji("Version")
EMOJI_STATISTICS = emoji("Statistics")
EMOJI_STARTTIME = emoji("StartTime")

# Статусные эмодзи
EMOJI_ERROR = emoji("ERROR")
EMOJI_WARNING = emoji("WARNING")
EMOJI_SUCCESS = emoji("SUCCESS")
EMOJI_LINK = emoji("DEFAULT")

# Типы контента
EMOJI_VIDEO = emoji("Video")

# Платформы и навигация
EMOJI_ARROW = emoji("Arrow")
EMOJI_TIKTOK = emoji("TikTok")
EMOJI_YOUTUBE = emoji("YouTube")
EMOJI_INSTAGRAM = emoji("Instagram")
EMOJI_YANDEXMUSIC = emoji("Yandex.Music")

# Рейтинги
EMOJI_FIRSTPLACE = emoji("FirstPlace")
EMOJI_SECONDPLACE = emoji("SecondPlace")
EMOJI_THIRDPLACE = emoji("ThirdPlace")

__all__ = [
    'emoji',
    
    'EMOJI_DJGURDA',
    'EMOJI_VERSION',
    'EMOJI_STATISTICS',
    'EMOJI_STARTTIME',
    
    'EMOJI_ERROR',
    'EMOJI_WARNING',
    'EMOJI_SUCCESS',
    'EMOJI_LINK',
    
    'EMOJI_VIDEO',
      
    'EMOJI_ARROW',
    'EMOJI_TIKTOK',
    'EMOJI_YOUTUBE',
    'EMOJI_INSTAGRAM',
    'EMOJI_YANDEXMUSIC',
    
    'EMOJI_FIRSTPLACE',
    'EMOJI_SECONDPLACE',
    'EMOJI_THIRDPLACE',
]
