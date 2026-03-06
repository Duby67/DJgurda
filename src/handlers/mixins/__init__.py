"""
Миксины для обработки медиа-контента.

Содержит классы-миксины для загрузки и обработки видео, аудио, фото и групп медиа.
Наследуются обработчиками конкретных платформ для переиспользования функциональности.
"""

from .video import VideoMixin
from .photo import PhotoMixin
from .audio import AudioMixin
from .media_group import MediaGroupMixin

__all__ = [
    'VideoMixin', 
    'PhotoMixin', 
    'AudioMixin', 
    'MediaGroupMixin'
]
