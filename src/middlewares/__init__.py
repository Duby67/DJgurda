"""
Промежуточный слой для бота.

Содержит компоненты промежуточного слоя для обработки входящих сообщений.
"""

from .bot_enabled import BotEnabledMiddleware

__all__ = [
    'BotEnabledMiddleware'
]
