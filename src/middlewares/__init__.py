"""
Промежуточное ПО (middleware) для бота.

Содержит middleware-компоненты для обработки входящих сообщений.
"""

from .bot_enabled import BotEnabledMiddleware

__all__ = [
    'BotEnabledMiddleware'
]
