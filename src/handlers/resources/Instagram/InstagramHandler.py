"""
Главный обработчик Instagram.

Определяет тип контента по URL и направляет в typed-процессоры.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from src.config import PROJECT_TEMP_DIR
from src.handlers.base import BaseHandler
from src.handlers.contracts import MediaResult

from .InstagramDependencies import InstagramCookieOptionsProvider, InstagramMediaGateway
from .InstagramMediaGroup import InstagramMediaGroup
from .InstagramProfile import InstagramProfile
from .InstagramReels import InstagramReels
from .InstagramStories import InstagramStories
from .InstagramUrlService import InstagramUrlService

logger = logging.getLogger(__name__)


class InstagramHandler(BaseHandler):
    """Обработчик ссылок Instagram: reels/media_group/stories/profile."""

    PATTERN = re.compile(r"https?://(?:www\.|m\.)?instagram\.com/\S+")

    def __init__(self) -> None:
        self._runtime_dir = PROJECT_TEMP_DIR / self.__class__.__name__
        self._runtime_dir.mkdir(parents=True, exist_ok=True)

        self._url_service = InstagramUrlService()
        self._options_provider = InstagramCookieOptionsProvider(runtime_dir=self._runtime_dir)
        self._media_gateway = InstagramMediaGateway(runtime_dir=self._runtime_dir)

        self._reels_processor = InstagramReels(
            media_gateway=self._media_gateway,
            options_provider=self._options_provider,
        )
        self._media_group_processor = InstagramMediaGroup(
            media_gateway=self._media_gateway,
            options_provider=self._options_provider,
        )
        self._stories_processor = InstagramStories(
            media_gateway=self._media_gateway,
            options_provider=self._options_provider,
        )
        self._profile_processor = InstagramProfile(
            media_gateway=self._media_gateway,
            options_provider=self._options_provider,
        )

    @property
    def pattern(self) -> re.Pattern:
        """Возвращает паттерн для распознавания Instagram URL."""
        return self.PATTERN

    @property
    def source_name(self) -> str:
        """Возвращает имя источника."""
        return "Instagram"

    async def process(
        self,
        url: str,
        context: str,
        resolved_url: Optional[str] = None,
    ) -> Optional[MediaResult]:
        """Основной вход в обработчик Instagram."""
        target_url = resolved_url or url
        normalized_url = self._url_service.normalize(target_url)
        if normalized_url != target_url:
            logger.debug("Normalized Instagram URL: %s -> %s", target_url, normalized_url)
        target_url = normalized_url

        content_type = self._url_service.detect_content_type(target_url)
        if content_type == "reels":
            logger.info("Instagram URL classified as reels: %s", target_url)
            return await self._reels_processor.process(target_url, context, original_url=url)
        if content_type == "media_group":
            logger.info("Instagram URL classified as media_group: %s", target_url)
            return await self._media_group_processor.process(target_url, context, original_url=url)
        if content_type == "stories":
            logger.info("Instagram URL classified as stories: %s", target_url)
            return await self._stories_processor.process(target_url, context, original_url=url)
        if content_type == "profile":
            logger.info("Instagram URL classified as profile: %s", target_url)
            return await self._profile_processor.process(target_url, context, original_url=url)

        logger.warning("Unsupported Instagram URL type: %s", target_url)
        return None