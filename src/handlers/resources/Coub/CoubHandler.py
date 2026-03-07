"""
Главный обработчик COUB.

Определяет тип контента по URL и направляет в профильный обработчик.
"""

import logging
import re
from typing import Any, Dict, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from src.handlers.base import BaseHandler

from .CoubVideo import CoubVideo

logger = logging.getLogger(__name__)


class CoubHandler(BaseHandler, CoubVideo):
    """
    Обработчик ссылок COUB.
    На текущем этапе поддерживается формат /view/<id>.
    """

    PATTERN = re.compile(r"https?://(?:www\.)?coub\.com/\S+")
    TRACKING_QUERY_PARAMS = frozenset({"si", "feature", "ref", "source"})

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

    def _normalize_coub_url(self, url: str) -> str:
        """
        Нормализует URL COUB и отбрасывает трекинговые query-параметры.
        """
        parts = urlsplit(url)
        netloc = parts.netloc.lower()
        if netloc == "coub.com":
            netloc = "www.coub.com"

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
        normalized_path = parts.path.rstrip("/") or "/"

        return urlunsplit(
            (
                parts.scheme,
                netloc,
                normalized_path,
                normalized_query,
                parts.fragment,
            )
        )

    def _detect_content_type(self, url: str) -> Optional[str]:
        """
        Определяет поддерживаемый тип COUB-контента.
        """
        parts = urlsplit(url)
        path_parts = [part for part in parts.path.split("/") if part]
        if len(path_parts) >= 2 and path_parts[0].lower() == "view":
            return "video"
        return None

    async def process(
        self,
        url: str,
        context: str,
        resolved_url: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Основной вход в обработчик COUB.
        """
        target_url = resolved_url or url
        normalized_url = self._normalize_coub_url(target_url)
        if normalized_url != target_url:
            logger.debug("Normalized COUB URL: %s -> %s", target_url, normalized_url)
        target_url = normalized_url

        content_type = self._detect_content_type(target_url)
        if content_type == "video":
            logger.info("COUB URL classified as video: %s", target_url)
            return await self._process_coub_video(target_url, context, original_url=url)

        logger.warning("Unsupported COUB URL type: %s", target_url)
        return None
