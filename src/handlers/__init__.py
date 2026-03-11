"""
Обработчики медиа-сообщений.

Содержит базовые классы и менеджеры для обработки контента из различных платформ.
"""

from .base import BaseHandler
from .manager import ServiceManager

__all__ = [
    'BaseHandler',
    'ServiceManager',
]
