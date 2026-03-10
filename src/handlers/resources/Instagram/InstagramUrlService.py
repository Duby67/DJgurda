"""
Явный URL API для Instagram-классификации.
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


class InstagramUrlService:
    """Нормализатор и классификатор Instagram URL."""

    TRACKING_QUERY_PARAMS = frozenset({"igshid", "igsh", "fbclid"})
    RESERVED_ROOT_PATHS = frozenset(
        {"p", "reel", "reels", "stories", "accounts", "explore", "direct", "tv"}
    )

    def normalize(self, url: str) -> str:
        """Нормализует Instagram URL и удаляет трекинговые query-параметры."""
        parts = urlsplit(url)
        netloc = parts.netloc.lower()
        if netloc in {"instagram.com", "m.instagram.com"}:
            netloc = "www.instagram.com"

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
        return urlunsplit((parts.scheme, netloc, parts.path, normalized_query, parts.fragment))

    def detect_content_type(self, url: str) -> str | None:
        """Определяет поддерживаемый тип Instagram-контента."""
        parts = urlsplit(url)
        path_parts = [part for part in parts.path.split("/") if part]
        if not path_parts:
            return None

        first_part = path_parts[0].lower()

        if first_part in {"reel", "reels"} and len(path_parts) >= 2:
            return "reels"

        if first_part == "p" and len(path_parts) >= 2:
            return "media_group"

        if first_part == "stories" and len(path_parts) >= 3:
            return "stories"

        if first_part not in self.RESERVED_ROOT_PATHS:
            return "profile"

        return None