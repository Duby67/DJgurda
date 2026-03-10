"""
Явный URL API для TikTok-классификации.
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


class TikTokUrlService:
    """Нормализатор и классификатор TikTok URL."""

    TRACKING_QUERY_PARAMS = frozenset({"_r", "_t"})

    def normalize(self, url: str) -> str:
        """Нормализует TikTok URL и удаляет только трекинговые query-параметры."""
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

    def detect_content_type(self, url: str) -> str:
        """Определяет поддерживаемый тип TikTok-контента (`video`/`photo`/`profile`)."""
        path = urlsplit(url).path.lower()
        if "/photo/" in path:
            return "photo"
        if "/video/" in path:
            return "video"
        return "profile"