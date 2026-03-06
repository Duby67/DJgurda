"""
Модуль Telegram бота.
Содержит обработчики команд, роутеры и логику бота.
"""

from .commands import command_routers
from .processing import media_router
from .lifespan import on_startup, on_shutdown

__all__ = [
    'command_routers', 
    'on_startup', 
    'on_shutdown',
    'media_router'
]