"""
Обработчики для различных медиа-платформ.

Каждый подмодуль содержит обработчики для конкретной платформы.
"""

from .TikTok import TikTokHandler
from .YouTube import YouTubeHandler
from .Instagram import InstagramHandler
from .Coub import CoubHandler
from .YandexMusic import YandexMusicHandler
from .VK import VKHandler

__all__ = [
    "TikTokHandler",
    "YouTubeHandler",
    "InstagramHandler",
    "CoubHandler",
    "YandexMusicHandler",
    "VKHandler",
]
