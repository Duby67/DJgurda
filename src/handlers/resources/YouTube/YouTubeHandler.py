"""
Главный обработчик YouTube.

Определяет тип контента по URL и направляет в typed-процессор.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from src.config import PROJECT_TEMP_DIR
from src.handlers.base import BaseHandler
from src.handlers.contracts import MediaResult

from .YouTubeChannel import YouTubeChannel
from .YouTubeDependencies import YouTubeCookieOptionsProvider, YouTubeMediaGateway
from .YouTubeShorts import YouTubeShorts
from .YouTubeUrlService import YouTubeUrlService

logger = logging.getLogger(__name__)


class YouTubeHandler(BaseHandler):
    """Обработчик ссылок YouTube (`shorts`, `channel`)."""

    PATTERN = re.compile(r"https?://(?:www\.|m\.)?(?:youtube\.com|youtu\.be)/\S+")

    def __init__(self) -> None:
        self._runtime_dir = PROJECT_TEMP_DIR / self.__class__.__name__
        self._runtime_dir.mkdir(parents=True, exist_ok=True)

        self._url_service = YouTubeUrlService()
        self._options_provider = YouTubeCookieOptionsProvider(runtime_dir=self._runtime_dir)
        self._media_gateway = YouTubeMediaGateway(runtime_dir=self._runtime_dir)

        self._shorts_processor = YouTubeShorts(
            media_gateway=self._media_gateway,
            options_provider=self._options_provider,
        )
        self._channel_processor = YouTubeChannel(
            media_gateway=self._media_gateway,
            options_provider=self._options_provider,
        )

    @property
    def pattern(self) -> re.Pattern:
        """Возвращает паттерн для распознавания YouTube URL."""
        return self.PATTERN

    @property
    def source_name(self) -> str:
        """Возвращает имя источника."""
        return "YouTube"

    async def process(
        self,
        url: str,
        context: str,
        resolved_url: Optional[str] = None,
    ) -> Optional[MediaResult]:
        """Основной вход в обработчик YouTube."""
        target_url = resolved_url or url
        normalized_url = self._url_service.normalize(target_url)
        if normalized_url != target_url:
            logger.debug("Normalized YouTube URL: %s -> %s", target_url, normalized_url)
        target_url = normalized_url

        content_type = self._url_service.detect_content_type(target_url)
        if content_type == "shorts":
            logger.info("YouTube URL classified as shorts: %s", target_url)
            return await self._shorts_processor.process(target_url, context, original_url=url)
        if content_type == "channel":
            logger.info("YouTube URL classified as channel: %s", target_url)
            return await self._channel_processor.process(target_url, context, original_url=url)

        logger.warning("Unsupported YouTube URL type: %s", target_url)
        return None