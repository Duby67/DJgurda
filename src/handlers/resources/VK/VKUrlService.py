"""
Явный URL API для VK Music-классификации.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


class VKUrlService:
    """Нормализатор и классификатор URL VK Music."""

    TRACK_PATH_PATTERN = re.compile(
        r"^audio(?P<owner>-?\d+)_(?P<audio>\d+)(?:_(?P<access_hash>[A-Za-z0-9]+))?/?$",
        re.IGNORECASE,
    )
    PLAYLIST_PATH_PATTERN = re.compile(
        r"^music/playlist/(?P<owner>-?\d+)_(?P<playlist>\d+)(?:_(?P<access_hash>[A-Za-z0-9]+))?/?$",
        re.IGNORECASE,
    )
    TRACKING_QUERY_PARAMS = frozenset(
        {
            "from",
            "w",
            "z",
            "utm_source",
            "utm_medium",
            "utm_campaign",
            "utm_term",
            "utm_content",
        }
    )

    def normalize(self, url: str) -> str:
        """Нормализует URL VK (домен + трекинговые query-параметры)."""
        parts = urlsplit(url)
        netloc = parts.netloc.lower()
        if netloc in {"vk.ru", "m.vk.ru", "vk.com", "m.vk.com"}:
            netloc = "vk.com"
        elif netloc == "www.vk.ru":
            netloc = "www.vk.com"

        query_items = parse_qsl(parts.query, keep_blank_values=True)
        filtered_items = [
            (key, value)
            for key, value in query_items
            if key.lower() not in self.TRACKING_QUERY_PARAMS
            and not key.lower().startswith("utm_")
        ]
        normalized_query = urlencode(filtered_items, doseq=True)
        normalized_path = parts.path.rstrip("/") or parts.path

        return urlunsplit((parts.scheme or "https", netloc, normalized_path, normalized_query, parts.fragment))

    def detect_content_type(self, url: str) -> tuple[str | None, re.Match[str] | None]:
        """Определяет поддерживаемый тип VK Music-контента."""
        path = urlsplit(url).path.strip("/")
        playlist_match = self.PLAYLIST_PATH_PATTERN.match(path)
        if playlist_match:
            return "playlist", playlist_match

        track_match = self.TRACK_PATH_PATTERN.match(path)
        if track_match:
            return "audio", track_match

        return None, None
