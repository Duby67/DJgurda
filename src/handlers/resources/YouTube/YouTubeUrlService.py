"""
Явный URL API для YouTube-классификации.
"""

from __future__ import annotations

from urllib.parse import parse_qs, parse_qsl, urlencode, urlsplit, urlunsplit


class YouTubeUrlService:
    """Нормализатор и классификатор YouTube URL."""

    TRACKING_QUERY_PARAMS = frozenset({"is", "si", "feature", "pp"})
    CHANNEL_ROOT_SEGMENTS = frozenset({"channel", "c", "user"})
    VIDEO_ROOT_SEGMENTS = frozenset({"watch", "live", "embed", "v"})

    def normalize(self, url: str) -> str:
        """Нормализует YouTube URL и удаляет только трекинговые query-параметры."""
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

    @staticmethod
    def _has_non_empty_query_value(query: dict[str, list[str]], key: str) -> bool:
        """Проверяет наличие непустого query-параметра."""
        return any(isinstance(value, str) and value.strip() for value in query.get(key, []))

    def detect_content_type(self, url: str) -> str | None:
        """Определяет поддерживаемый тип YouTube-контента."""
        parts = urlsplit(url)
        host = parts.netloc.lower()
        path_parts = [part for part in parts.path.split("/") if part]
        query = parse_qs(parts.query)

        if host == "youtu.be" and path_parts:
            return "video"

        if not path_parts:
            return "playlist" if self._has_non_empty_query_value(query, "list") else None

        first_part = path_parts[0].lower()

        if first_part == "shorts" and len(path_parts) >= 2:
            return "shorts"

        if first_part == "clip" and len(path_parts) >= 2:
            return "clip"

        if first_part == "playlist" and self._has_non_empty_query_value(query, "list"):
            return "playlist"

        if first_part == "watch":
            if self._has_non_empty_query_value(query, "v"):
                return "video"
            if self._has_non_empty_query_value(query, "list"):
                return "playlist"
            return None

        if first_part in self.VIDEO_ROOT_SEGMENTS and len(path_parts) >= 2:
            return "video"

        if path_parts[0].startswith("@"):
            return "channel"

        if first_part in self.CHANNEL_ROOT_SEGMENTS and len(path_parts) >= 2:
            return "channel"

        return None
