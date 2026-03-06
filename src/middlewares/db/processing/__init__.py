"""
Модули обработки данных базы данных.

Содержит CRUD операции для работы с настройками и статистикой.
"""

from .bot_settings_processor import (
    get_bot_enabled,
    set_bot_enabled,
    get_errors_enabled,
    set_errors_enabled,
    get_notifications_enabled,
    set_notifications_enabled,
    get_chats_with_notifications_enabled
)

from .stats_processor import (
    update_stats,
    get_chat_stats
)

__all__ = [
    'get_bot_enabled',
    'set_bot_enabled',
    'get_errors_enabled',
    'set_errors_enabled',
    'get_notifications_enabled',
    'set_notifications_enabled',
    'get_chats_with_notifications_enabled',
    'update_stats',
    'get_chat_stats'
]
