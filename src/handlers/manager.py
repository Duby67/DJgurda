"""
Менеджер сервисов для обработки медиа.
"""

import logging
from typing import List, Optional

from .base import BaseHandler
from src.handlers.resources import TikTokHandler

logger = logging.getLogger(__name__)


class ServiceManager:
    """
    Менеджер для регистрации и поиска обработчиков медиа.
    """
    
    def __init__(self) -> None:
        """
        Инициализирует менеджер с зарегистрированными обработчиками.
        """
        active_handler_classes = (TikTokHandler,)
        self.handlers: List[BaseHandler] = [handler_cls() for handler_cls in active_handler_classes]
        logger.info(f"Зарегистрировано обработчиков: {len(self.handlers)}")

    def get_handler(self, url: str) -> Optional[BaseHandler]:
        """
        Находит обработчик, поддерживающий данный URL.
        
        Args:
            url: URL для обработки
            
        Returns:
            BaseHandler или None если подходящий обработчик не найден
        """
        for handler in self.handlers:
            if handler.pattern.search(url):
                logger.debug(f"Найден обработчик для {url}: {handler.source_name}")
                return handler
        logger.debug(f"Не найден обработчик для URL: {url}")
        return None
