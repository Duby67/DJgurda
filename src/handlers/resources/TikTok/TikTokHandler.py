"""
Главный обработчик для платформы TikTok.

Определяет тип контента по URL и направляет в typed-процессоры.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from src.config import PROJECT_TEMP_DIR
from src.handlers.base import BaseHandler
from src.handlers.contracts import MediaResult

from .TikTokDependencies import TikTokCookieOptionsProvider, TikTokMediaGateway
from .TikTokPhoto import TikTokPhoto
from .TikTokProfile import TikTokProfile
from .TikTokUrlService import TikTokUrlService
from .TikTokVideo import TikTokVideo

logger = logging.getLogger(__name__)


class TikTokHandler(BaseHandler):
    """Обработчик контента TikTok (`video`, `profile`, `media_group`)."""

    PATTERN = re.compile(
        r"https?://(?:www\.|m\.)?(?:tiktok\.com|vt\.tiktok\.com|vm\.tiktok\.com)\S+"
    )

    def __init__(self) -> None:
        self._runtime_dir = PROJECT_TEMP_DIR / self.__class__.__name__
        self._runtime_dir.mkdir(parents=True, exist_ok=True)

        self._url_service = TikTokUrlService()
        self._options_provider = TikTokCookieOptionsProvider(runtime_dir=self._runtime_dir)
        self._media_gateway = TikTokMediaGateway(runtime_dir=self._runtime_dir)

        self._video_processor = TikTokVideo(
            media_gateway=self._media_gateway,
            options_provider=self._options_provider,
        )
        self._photo_processor = TikTokPhoto(
            media_gateway=self._media_gateway,
            options_provider=self._options_provider,
        )
        self._profile_processor = TikTokProfile(media_gateway=self._media_gateway)

    @property
    def pattern(self) -> re.Pattern:
        """Возвращает паттерн для распознавания URL TikTok."""
        return self.PATTERN

    @property
    def source_name(self) -> str:
        """Возвращает название источника."""
        return "TikTok"

    async def process(
        self,
        url: str,
        context: str,
        resolved_url: Optional[str] = None,
    ) -> Optional[MediaResult]:
        """Основной вход в обработчик TikTok."""
        target_url = resolved_url or url
        normalized_url = self._url_service.normalize(target_url)
        if normalized_url != target_url:
            logger.debug("Normalized TikTok URL: %s -> %s", target_url, normalized_url)
        target_url = normalized_url

        content_type = self._url_service.detect_content_type(target_url)
        if content_type == "photo":
            logger.info("TikTok URL classified as photo/media_group: %s", target_url)
            return await self._photo_processor.process(target_url, context, original_url=url)
        if content_type == "video":
            logger.info("TikTok URL classified as video: %s", target_url)
            return await self._video_processor.process(target_url, context, original_url=url)

        logger.info("TikTok URL classified as profile: %s", target_url)
        return await self._profile_processor.process(target_url, context, original_url=url)