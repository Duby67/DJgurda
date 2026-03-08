"""
Менеджер сервисов для обработки медиа.
"""

import logging
from typing import List, Optional

from .base import BaseHandler
from src.handlers.resources import CoubHandler, InstagramHandler, TikTokHandler, VKHandler, YouTubeHandler

logger = logging.getLogger(__name__)


class ServiceManager:
    """
    Менеджер для регистрации и поиска обработчиков медиа.
    """
    
    def __init__(self) -> None:
        """
        Инициализирует менеджер с зарегистрированными обработчиками.
        """
        active_handler_classes = (
            TikTokHandler,
            YouTubeHandler,
            InstagramHandler,
            CoubHandler,
            VKHandler,
        )
        self.handlers: List[BaseHandler] = [handler_cls() for handler_cls in active_handler_classes]
        logger.info(f"Registered handlers: {len(self.handlers)}")

    def get_handler(self, url: str) -> Optional[BaseHandler]:
        """
        Находит обработчик, поддерживающий данный URL.
        
        Аргументы:
            url: URL для обработки
            
        Возвращает:
            BaseHandler или None если подходящий обработчик не найден
        """
        for handler in self.handlers:
            if handler.pattern.search(url):
                logger.debug(f"Handler found for {url}: {handler.source_name}")
                return handler
        logger.debug(f"No handler found for URL: {url}")
        return None
