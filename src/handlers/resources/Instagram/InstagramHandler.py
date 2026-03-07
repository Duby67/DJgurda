"""
Главный обработчик Instagram.

Определяет тип контента по URL и направляет на профильный обработчик.
"""

import logging
import re
from typing import Any, Dict, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from src.handlers.base import BaseHandler

from .InstagramMediaGroup import InstagramMediaGroup
from .InstagramProfile import InstagramProfile
from .InstagramReels import InstagramReels
from .InstagramStories import InstagramStories

logger = logging.getLogger(__name__)


class InstagramHandler(
    BaseHandler,
    InstagramReels,
    InstagramMediaGroup,
    InstagramStories,
    InstagramProfile,
):
    """
    Обработчик ссылок Instagram: reels/media_group/stories/profile.
    """

    PATTERN = re.compile(r"https?://(?:www\.|m\.)?instagram\.com/\S+")
    TRACKING_QUERY_PARAMS = frozenset({"igshid", "igsh", "fbclid"})
    RESERVED_ROOT_PATHS = frozenset(
        {"p", "reel", "reels", "stories", "accounts", "explore", "direct", "tv"}
    )

    @property
    def pattern(self) -> re.Pattern:
        """
        Возвращает паттерн для распознавания Instagram URL.
        """
        return self.PATTERN

    @property
    def source_name(self) -> str:
        """
        Возвращает имя источника.
        """
        return "Instagram"

    def _normalize_instagram_url(self, url: str) -> str:
        """
        Нормализует домен и отбрасывает трекинговые query-параметры.
        """
        parts = urlsplit(url)
        netloc = parts.netloc.lower()
        if netloc in {"instagram.com", "m.instagram.com"}:
            netloc = "www.instagram.com"

        query_items = parse_qsl(parts.query, keep_blank_values=True)
        filtered_items = []
        for key, value in query_items:
            key_lower = key.lower()
            if key_lower in self.TRACKING_QUERY_PARAMS:
                continue
            if key_lower.startswith("utm_"):
                continue
            filtered_items.append((key, value))

        normalized_query = urlencode(filtered_items, doseq=True)
        return urlunsplit((parts.scheme, netloc, parts.path, normalized_query, parts.fragment))

    def _detect_content_type(self, url: str) -> Optional[str]:
        """
        Определяет тип Instagram-контента по URL.
        """
        parts = urlsplit(url)
        path_parts = [part for part in parts.path.split("/") if part]
        if not path_parts:
            return None

        first_part = path_parts[0].lower()

        if first_part in {"reel", "reels"} and len(path_parts) >= 2:
            return "reels"

        if first_part == "p" and len(path_parts) >= 2:
            return "media_group"

        if first_part == "stories" and len(path_parts) >= 3:
            return "stories"

        if first_part not in self.RESERVED_ROOT_PATHS:
            return "profile"

        return None

    async def process(
        self,
        url: str,
        context: str,
        resolved_url: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Основной вход в обработчик Instagram.
        """
        target_url = resolved_url or url
        normalized_url = self._normalize_instagram_url(target_url)
        if normalized_url != target_url:
            logger.debug("Normalized Instagram URL: %s -> %s", target_url, normalized_url)
        target_url = normalized_url

        content_type = self._detect_content_type(target_url)
        if content_type == "reels":
            logger.info("Instagram URL classified as reels: %s", target_url)
            return await self._process_instagram_reels(target_url, context, original_url=url)
        if content_type == "media_group":
            logger.info("Instagram URL classified as media_group: %s", target_url)
            return await self._process_instagram_media_group(target_url, context, original_url=url)
        if content_type == "stories":
            logger.info("Instagram URL classified as stories: %s", target_url)
            return await self._process_instagram_stories(target_url, context, original_url=url)
        if content_type == "profile":
            logger.info("Instagram URL classified as profile: %s", target_url)
            return await self._process_instagram_profile(target_url, context, original_url=url)

        logger.warning("Unsupported Instagram URL type: %s", target_url)
        return None

