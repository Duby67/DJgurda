"""
Тесты для middleware бота.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from aiogram.types import Message, Chat, User

from src.middlewares.bot_enabled import BotEnabledMiddleware


@pytest.mark.asyncio
async def test_middleware_with_bot_enabled():
    """Тест middleware при включенном боте."""
    middleware = BotEnabledMiddleware()
    handler = AsyncMock()
    message = MagicMock(spec=Message)
    message.text = "тестовое сообщение"
    message.chat.id = 123
    
    # Мокаем функцию проверки состояния бота
    with pytest.MonkeyPatch().context() as m:
        m.setattr('src.middlewares.db.get_bot_enabled', AsyncMock(return_value=True))
        
        await middleware(handler, message, {})
        handler.assert_called_once()


@pytest.mark.asyncio
async def test_middleware_with_bot_disabled():
    """Тест middleware при отключенном боте."""
    middleware = BotEnabledMiddleware()
    handler = AsyncMock()
    message = MagicMock(spec=Message)
    message.text = "тестовое сообщение"
    message.chat.id = 123
    
    with pytest.MonkeyPatch().context() as m:
        m.setattr('src.middlewares.db.get_bot_enabled', AsyncMock(return_value=False))
        
        await middleware(handler, message, {})
        handler.assert_not_called()


@pytest.mark.asyncio
async def test_middleware_management_commands():
    """Тест middleware для команд управления."""
    middleware = BotEnabledMiddleware()
    handler = AsyncMock()
    
    # Тестируем команду /start
    message_start = MagicMock(spec=Message)
    message_start.text = "/start"
    message_start.chat.id = 123
    
    with pytest.MonkeyPatch().context as m:
        m.setattr('src.middlewares.db.get_bot_enabled', AsyncMock(return_value=False))
        
        await middleware(handler, message_start, {})
        handler.assert_called_once()
    
    # Тестируем команду /toggle_bot
    handler.reset_mock()
    message_toggle = MagicMock(spec=Message)
    message_toggle.text = "/toggle_bot"
    message_toggle.chat.id = 123
    
    with pytest.MonkeyPatch().context as m:
        m.setattr('src.middlewares.db.get_bot_enabled', AsyncMock(return_value=False))
        
        await middleware(handler, message_toggle, {})
        handler.assert_called_once()
