"""
Главный обработчик YouTube.

Определяет тип контента по URL и направляет в профильный обработчик.
"""

import logging
import re
from typing import Any, Dict, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from src.handlers.base import BaseHandler

from .YouTubeChannel import YouTubeChannel
from .YouTubeShorts import YouTubeShorts

logger = logging.getLogger(__name__)


class YouTubeHandler(BaseHandler, YouTubeShorts, YouTubeChannel):
    """
    Обработчик ссылок YouTube (Shorts и страницы каналов).
    """

    PATTERN = re.compile(r"https?://(?:www\.|m\.)?(?:youtube\.com|youtu\.be)/\S+")
    TRACKING_QUERY_PARAMS = frozenset({"si", "feature", "pp"})

    @property
    def pattern(self) -> re.Pattern:
        """
        Возвращает паттерн для распознавания YouTube URL.
        """
        return self.PATTERN

    @property
    def source_name(self) -> str:
        """
        Возвращает имя источника.
        """
        return "YouTube"

    def _normalize_youtube_url(self, url: str) -> str:
        """
        Нормализует домен и удаляет только трекинговые query-параметры.
        """
        parts = urlsplit(url)
        netloc = parts.netloc.lower()
        if netloc in {"youtube.com", "m.youtube.com"}:
            netloc = "www.youtube.com"

        query_items = parse_qsl(parts.query, keep_blank_values=True)
        filtered_items = [
            (key, value)
            for key, value in query_items
            if key not in self.TRACKING_QUERY_PARAMS
        ]
        normalized_query = urlencode(filtered_items, doseq=True)

        return urlunsplit((parts.scheme, netloc, parts.path, normalized_query, parts.fragment))

    def _detect_content_type(self, url: str) -> Optional[str]:
        """
        Определяет тип YouTube-контента.
        """
        parts = urlsplit(url)
        path_parts = [part for part in parts.path.split("/") if part]
        if not path_parts:
            return None

        first_part = path_parts[0].lower()

        if first_part == "shorts" and len(path_parts) >= 2:
            return "shorts"

        if path_parts[0].startswith("@"):
            return "channel"

        if first_part in {"channel", "c", "user"} and len(path_parts) >= 2:
            return "channel"

        return None

    async def process(
        self,
        url: str,
        context: str,
        resolved_url: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Основной вход в обработчик YouTube.
        """
        target_url = resolved_url or url
        normalized_url = self._normalize_youtube_url(target_url)
        if normalized_url != target_url:
            logger.debug("Normalized YouTube URL: %s -> %s", target_url, normalized_url)
        target_url = normalized_url

        content_type = self._detect_content_type(target_url)
        if content_type == "shorts":
            logger.info("YouTube URL classified as shorts: %s", target_url)
            return await self._process_youtube_shorts(target_url, context, original_url=url)
        if content_type == "channel":
            logger.info("YouTube URL classified as channel: %s", target_url)
            return await self._process_youtube_channel(target_url, context, original_url=url)

        logger.warning("Unsupported YouTube URL type: %s", target_url)
        return None

