"""
Явный URL API для Coub-классификации.
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


class CoubUrlService:
    """Нормализатор и классификатор URL Coub."""

    TRACKING_QUERY_PARAMS = frozenset({"si", "feature", "ref", "source"})

    def normalize(self, url: str) -> str:
        """Нормализует URL Coub и удаляет трекинговые query-параметры."""
        parts = urlsplit(url)
        netloc = parts.netloc.lower()
        if netloc == "coub.com":
            netloc = "www.coub.com"

        query_items = parse_qsl(parts.query, keep_blank_values=True)
        filtered_items = [
            (key, value)
            for key, value in query_items
            if key.lower() not in self.TRACKING_QUERY_PARAMS and not key.lower().startswith("utm_")
        ]

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

    def detect_content_type(self, url: str) -> str | None:
        """Определяет поддерживаемый тип Coub-контента."""
        path_parts = [part for part in urlsplit(url).path.split("/") if part]
        if len(path_parts) >= 2 and path_parts[0].lower() == "view":
            return "video"
        return None
