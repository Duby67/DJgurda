"""
Явный URL API для YouTube-классификации.
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


class YouTubeUrlService:
    """Нормализатор и классификатор YouTube URL."""

    TRACKING_QUERY_PARAMS = frozenset({"si", "feature", "pp"})

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

    def detect_content_type(self, url: str) -> str | None:
        """Определяет поддерживаемый тип YouTube-контента (`shorts` или `channel`)."""
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