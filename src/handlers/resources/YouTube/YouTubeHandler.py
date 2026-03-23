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
from .YouTubeClip import YouTubeClip
from .YouTubeDependencies import YouTubeCookieOptionsProvider, YouTubeMediaGateway
from .YouTubePlaylist import YouTubePlaylist
from .YouTubeShorts import YouTubeShorts
from .YouTubeUrlService import YouTubeUrlService
from .YouTubeVideo import YouTubeVideo

logger = logging.getLogger(__name__)


class YouTubeHandler(BaseHandler):
    """Обработчик ссылок YouTube (`video`, `shorts`, `clip`, `channel`, `playlist`)."""

    PATTERN = re.compile(r"https?://(?:www\.|m\.)?(?:youtube\.com|youtu\.be)/\S+")
    _SPECIFIC_CONTENT_TYPES = frozenset({"shorts", "clip", "channel", "playlist"})

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
        self._video_processor = YouTubeVideo(
            media_gateway=self._media_gateway,
            options_provider=self._options_provider,
        )
        self._clip_processor = YouTubeClip(
            media_gateway=self._media_gateway,
            options_provider=self._options_provider,
        )
        self._channel_processor = YouTubeChannel(
            media_gateway=self._media_gateway,
            options_provider=self._options_provider,
        )
        self._playlist_processor = YouTubePlaylist(
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

    def _pick_target_url(
        self,
        *,
        original_url: str,
        resolved_url: Optional[str],
    ) -> tuple[str, str | None]:
        """
        Выбирает URL для дальнейшей обработки и определяет его content type.

        Если `resolved_url` приводит короткую/специфичную ссылку к более общему
        `watch`-формату, сохраняем исходную intent-семантику пользователя.
        """
        normalized_original = self._url_service.normalize(original_url)
        original_type = self._url_service.detect_content_type(normalized_original)

        if not resolved_url:
            return normalized_original, original_type

        normalized_resolved = self._url_service.normalize(resolved_url)
        resolved_type = self._url_service.detect_content_type(normalized_resolved)

        if original_type in self._SPECIFIC_CONTENT_TYPES and resolved_type in {None, "video"}:
            logger.debug(
                "Keeping original YouTube URL for specific content type: %s -> %s",
                normalized_original,
                normalized_resolved,
            )
            return normalized_original, original_type

        return normalized_resolved, resolved_type

    async def process(
        self,
        url: str,
        context: str,
        resolved_url: Optional[str] = None,
    ) -> Optional[MediaResult]:
        """Основной вход в обработчик YouTube."""
        target_url, content_type = self._pick_target_url(
            original_url=url,
            resolved_url=resolved_url,
        )
        if content_type == "video":
            logger.info("YouTube URL classified as video: %s", target_url)
            return await self._video_processor.process(target_url, context, original_url=url)
        if content_type == "shorts":
            logger.info("YouTube URL classified as shorts: %s", target_url)
            return await self._shorts_processor.process(target_url, context, original_url=url)
        if content_type == "clip":
            logger.info("YouTube URL classified as clip: %s", target_url)
            return await self._clip_processor.process(target_url, context, original_url=url)
        if content_type == "channel":
            logger.info("YouTube URL classified as channel: %s", target_url)
            return await self._channel_processor.process(target_url, context, original_url=url)
        if content_type == "playlist":
            logger.info("YouTube URL classified as playlist: %s", target_url)
            return await self._playlist_processor.process(target_url, context, original_url=url)

        logger.warning("Unsupported YouTube URL type: %s", target_url)
        return None
