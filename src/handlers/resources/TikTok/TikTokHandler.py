"""
Главный обработчик для платформы TikTok.

Определяет тип контента по URL и направляет на соответствующий обработчик.
"""

import re
from typing import Optional, Dict, Any

from .TikTokVideo import TikTokVideo
from .TikTokPhoto import TikTokPhoto
from .TikTokProfile import TikTokProfile
from src.handlers.base import BaseHandler

class TikTokHandler(BaseHandler, TikTokVideo, TikTokPhoto, TikTokProfile):
    """
    Обработчик контента с TikTok.
    
    Наследует функциональность от специализированных классов для разных типов контента.
    """
    
    # Паттерн для определения URL TikTok
    PATTERN = re.compile(
        r'https?://(?:www\.|m\.)?(?:tiktok\.com|vt\.tiktok\.com|vm\.tiktok\.com)\S+'
    )

    @property
    def pattern(self) -> re.Pattern:
        """Возвращает паттерн для распознавания URL TikTok."""
        return self.PATTERN

    @property
    def source_name(self) -> str:
        """Возвращает название источника."""
        return "TikTok"

    async def process(self, url: str, context: str, resolved_url: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Обрабатывает URL TikTok и возвращает информацию о контенте.
        
        Аргументы:
            url: Исходный URL
            context: Контекст сообщения
            resolved_url: Разрешенный URL (после редиректов)
            
        Возвращает:
            Словарь с информацией о контенте или None при ошибке
        """
        target_url = resolved_url or url
        
        # Определяем тип контента по пути URL
        if '/photo/' in target_url:
            return await self._process_tiktok_photo(target_url, context)
        elif '/video/' in target_url:
            return await self._process_tiktok_video(target_url, context)
        else:
            # Предполагаем, что это профиль
            return await self._process_tiktok_profile(target_url, context)
