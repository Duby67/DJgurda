"""
Middleware для проверки включения бота в чате.

Проверяет, разрешена ли работа бота в текущем чате.
Команды /start и /toggle_bot обрабатываются всегда для возможности управления.
"""

import logging
from typing import Callable, Dict, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import Message

from src.middlewares.db import get_bot_enabled

logger = logging.getLogger(__name__)

class BotEnabledMiddleware(BaseMiddleware):
    """
    Middleware для проверки состояния бота в чате.
    
    Пропускает команды управления (/start, /toggle_bot) всегда.
    Для остальных сообщений проверяет настройки чата.
    """
    
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        """
        Обрабатывает входящее сообщение через middleware.
        
        Args:
            handler: Следующий обработчик в цепочке
            event: Входящее сообщение
            data: Данные контекста
            
        Returns:
            Результат обработчика или None если бот отключен
        """
        try:
            # Проверяем, есть ли текст в сообщении
            if not event.text:
                # Для медиа-сообщений без текста проверяем состояние бота
                enabled = await get_bot_enabled(event.chat.id)
                if enabled:
                    return await handler(event, data)
                else:
                    logger.debug(f"Бот отключен в чате {event.chat.id}, медиа-сообщение пропущено")
                    return
            
            # Команды управления всегда пропускаются
            is_start_command = event.text.startswith("/start")
            is_toggle_command = event.text.startswith("/toggle_bot")
            
            if is_start_command or is_toggle_command:
                logger.debug(f"Команда управления пропущена: {event.text}")
                return await handler(event, data)
            
            # Для остальных сообщений проверяем состояние бота
            enabled = await get_bot_enabled(event.chat.id)
            if enabled:
                return await handler(event, data)
            else:
                logger.debug(f"Бот отключен в чате {event.chat.id}, сообщение пропущено: {event.text}")
                return
                
        except Exception as e:
            logger.exception(f"Ошибка в BotEnabledMiddleware для чата {event.chat.id}")
            # При ошибке пропускаем сообщение для сохранения функциональности
            return await handler(event, data)
