"""
Модули для работы с базой данных.

Включает модели, CRUD операции и обработчики данных.
Предоставляет асинхронный интерфейс для работы с SQLite.
"""

from .core import engine, AsyncSessionLocal, init_db, close_db
from .models import Base, BotSettings, Source, Stats
from .processing.bot_settings_processor import (
    get_bot_enabled, 
    set_bot_enabled,
    get_errors_enabled,
    set_errors_enabled, 
    get_notifications_enabled,
    set_notifications_enabled,
    get_chats_with_notifications_enabled
)
from .processing.stats_processor import (
    get_chat_stats,
    update_stats
)

__all__ = [
    # Ядро БД
    'engine',
    'AsyncSessionLocal',
    'init_db',
    'close_db',
    
    # Модели
    'Base',
    'BotSettings', 
    'Source',
    'Stats',
    
    # Обработчики настроек
    'get_bot_enabled',
    'set_bot_enabled', 
    'get_errors_enabled',
    'set_errors_enabled',
    'get_notifications_enabled',
    'set_notifications_enabled',
    'get_chats_with_notifications_enabled',
    
    # Обработчики статистики
    'get_chat_stats',
    'update_stats'
]
