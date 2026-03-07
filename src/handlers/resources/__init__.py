"""
Обработчики для различных медиа-платформ.

Каждый подмодуль содержит обработчики для конкретной платформы.
"""

from .TikTok import TikTokHandler
from .YouTube import YouTubeHandler
from .Instagram import InstagramHandler

__all__ = ["TikTokHandler", "YouTubeHandler", "InstagramHandler"]
