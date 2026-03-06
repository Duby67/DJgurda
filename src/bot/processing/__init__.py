"""
Модуль обработки медиа-сообщений.

Содержит компоненты для извлечения, обработки и маршрутизации медиа-контента.
"""

from .link_extractor import split_into_blocks, get_user_link
from .media_processor import process_block
from .media_router import router as media_router

__all__ = [
    'split_into_blocks',
    'get_user_link', 
    'process_block',
    'media_router'
]