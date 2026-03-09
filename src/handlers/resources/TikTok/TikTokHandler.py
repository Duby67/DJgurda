"""
Главный обработчик для платформы TikTok.

Определяет тип контента по URL и направляет на соответствующий обработчик.
"""

import re
import logging
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from typing import Optional, Dict, Any

from .TikTokVideo import TikTokVideo
from .TikTokPhoto import TikTokPhoto
from .TikTokProfile import TikTokProfile
from src.handlers.base import BaseHandler
from src.config import TIKTOK_COOKIES, TIKTOK_COOKIES_ENABLED
from src.utils.cookies import CookieFile

logger = logging.getLogger(__name__)

class TikTokHandler(BaseHandler, TikTokVideo, TikTokPhoto, TikTokProfile):
    """
    Обработчик контента с TikTok.
    
    Наследует функциональность от специализированных классов для разных типов контента.
    """
    
    # Паттерн для определения URL TikTok
    PATTERN = re.compile(
        r'https?://(?:www\.|m\.)?(?:tiktok\.com|vt\.tiktok\.com|vm\.tiktok\.com)\S+'
    )
    TRACKING_QUERY_PARAMS = frozenset({"_r", "_t"})

    def __init__(self) -> None:
        super().__init__()
        self._tiktok_cookies = CookieFile(
            provider_key="tiktok",
            provider_name="TikTok",
            enabled=TIKTOK_COOKIES_ENABLED,
            cookie_path=TIKTOK_COOKIES,
            path_env_name="TIKTOK_COOKIES_PATH",
            runtime_dir=self.temp_dir,
            log=logger,
        )

    @property
    def pattern(self) -> re.Pattern:
        """Возвращает паттерн для распознавания URL TikTok."""
        return self.PATTERN

    @property
    def source_name(self) -> str:
        """Возвращает название источника."""
        return "TikTok"

    def _build_tiktok_cookie_opts(self) -> Dict[str, str]:
        """
        Единая точка подключения TikTok cookies для yt-dlp.
        """
        return self._tiktok_cookies.build_ytdlp_opts()

    def _normalize_tiktok_url(self, url: str) -> str:
        """
        Удаляет трекинговые query-параметры TikTok, не затрагивая остальные.
        """
        parts = urlsplit(url)
        if not parts.query:
            return url

        query_items = parse_qsl(parts.query, keep_blank_values=True)
        filtered_items = [
            (key, value)
            for key, value in query_items
            if key not in self.TRACKING_QUERY_PARAMS
        ]

        if len(filtered_items) == len(query_items):
            return url

        normalized_query = urlencode(filtered_items, doseq=True)
        return urlunsplit((
            parts.scheme,
            parts.netloc,
            parts.path,
            normalized_query,
            parts.fragment,
        ))

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
        normalized_url = self._normalize_tiktok_url(target_url)
        if normalized_url != target_url:
            logger.debug("Normalized TikTok URL: %s -> %s", target_url, normalized_url)
        target_url = normalized_url
        
        # Определяем тип контента по пути URL
        if '/photo/' in target_url:
            return await self._process_tiktok_photo(target_url, context)
        elif '/video/' in target_url:
            return await self._process_tiktok_video(target_url, context)
        else:
            # Предполагаем, что это профиль
            return await self._process_tiktok_profile(target_url, context)
