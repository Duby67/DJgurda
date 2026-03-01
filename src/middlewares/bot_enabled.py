import logging

from aiogram import BaseMiddleware
from aiogram.types import Message
from typing import Callable, Dict, Any, Awaitable

from src.middlewares.db import get_bot_enabled

logger = logging.getLogger(__name__)

class BotEnabledMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        try:
            _is_start = event.text.startswith("/start")
            _is_toggle_bot = event.text.startswith("/toggle_bot")
            if event.text:
                if _is_start or _is_toggle_bot :
                    return await handler(event, data)

            enabled = await get_bot_enabled(event.chat.id)
            if enabled:
                return await handler(event, data)
            else:
                return
        except Exception as e:
            logger.exception(f"Ошибка в BotEnabledMiddleware для chat {event.chat.id}")
            return await handler(event, data)