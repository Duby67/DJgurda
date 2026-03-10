"""
Главный обработчик COUB.

Определяет тип контента по URL и направляет в typed-процессор.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from src.config import PROJECT_TEMP_DIR
from src.handlers.base import BaseHandler
from src.handlers.contracts import MediaResult

from .CoubDependencies import CoubMediaGateway, CoubYtdlpOptionsProvider
from .CoubVideo import CoubVideo
from .CoubUrlService import CoubUrlService

logger = logging.getLogger(__name__)


class CoubHandler(BaseHandler):
    """
    Обработчик ссылок COUB.
    На текущем этапе поддерживается формат /view/<id>.
    """

    PATTERN = re.compile(r"https?://(?:www\.)?coub\.com/\S+")

    def __init__(self) -> None:
        self._runtime_dir = PROJECT_TEMP_DIR / self.__class__.__name__
        self._runtime_dir.mkdir(parents=True, exist_ok=True)

        self._url_service = CoubUrlService()
        self._options_provider = CoubYtdlpOptionsProvider()
        self._media_gateway = CoubMediaGateway(runtime_dir=self._runtime_dir)
        self._video_processor = CoubVideo(
            media_gateway=self._media_gateway,
            options_provider=self._options_provider,
        )

    @property
    def pattern(self) -> re.Pattern:
        """
        Возвращает паттерн распознавания URL COUB.
        """
        return self.PATTERN

    @property
    def source_name(self) -> str:
        """
        Возвращает имя источника.
        """
        return "COUB"

    async def process(
        self,
        url: str,
        context: str,
        resolved_url: Optional[str] = None,
    ) -> Optional[MediaResult]:
        """
        Основной вход в обработчик COUB.
        """
        target_url = resolved_url or url
        normalized_url = self._url_service.normalize(target_url)
        if normalized_url != target_url:
            logger.debug("Normalized COUB URL: %s -> %s", target_url, normalized_url)
        target_url = normalized_url

        content_type = self._url_service.detect_content_type(target_url)
        if content_type == "video":
            logger.info("COUB URL classified as video: %s", target_url)
            return await self._video_processor.process(target_url, context, original_url=url)

        logger.warning("Unsupported COUB URL type: %s", target_url)
        return None
