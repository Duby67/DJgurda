"""
Явный URL API для VK-классификации.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


class VKUrlService:
    """Нормализатор и классификатор URL VK."""

    TRACK_PATH_PATTERN = re.compile(
        r"^audio(?P<owner>-?\d+)_(?P<audio>\d+)(?:_(?P<access_hash>[A-Za-z0-9]+))?/?$",
        re.IGNORECASE,
    )
    PLAYLIST_PATH_PATTERN = re.compile(
        r"^music/playlist/(?P<owner>-?\d+)_(?P<playlist>\d+)(?:_(?P<access_hash>[A-Za-z0-9]+))?/?$",
        re.IGNORECASE,
    )
    CLIP_PATH_PATTERN = re.compile(
        r"^clip(?P<owner>-?\d+)_(?P<clip>\d+)/?$",
        re.IGNORECASE,
    )
    WALL_POST_PATH_PATTERN = re.compile(
        r"^wall(?P<owner>-?\d+)_(?P<post>\d+)/?$",
        re.IGNORECASE,
    )
    PROFILE_ID_PATTERN = re.compile(
        r"^id(?P<profile_id>\d+)/?$",
        re.IGNORECASE,
    )
    RESERVED_COMMUNITY_PREFIXES = (
        "audio",
        "wall",
        "id",
        "video",
        "clip",
        "music",
        "feed",
        "login",
        "badbrowser.php",
    )
    COMMUNITY_PATTERN = re.compile(
        r"^(?P<screen_name>[A-Za-z0-9_.-]+)/?$",
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
        if netloc in {"vk.ru", "m.vk.ru", "vk.com", "m.vk.com", "vkvideo.ru", "m.vkvideo.ru"}:
            netloc = "vk.com"
        elif netloc == "www.vk.ru":
            netloc = "www.vk.com"
        elif netloc == "www.vkvideo.ru":
            netloc = "vk.com"

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
        """Определяет поддерживаемый тип VK-контента."""
        path = urlsplit(url).path.strip("/")
        playlist_match = self.PLAYLIST_PATH_PATTERN.match(path)
        if playlist_match:
            return "playlist", playlist_match

        track_match = self.TRACK_PATH_PATTERN.match(path)
        if track_match:
            return "audio", track_match

        clip_match = self.CLIP_PATH_PATTERN.match(path)
        if clip_match:
            return "clip", clip_match

        wall_post_match = self.WALL_POST_PATH_PATTERN.match(path)
        if wall_post_match:
            return "post", wall_post_match

        profile_id_match = self.PROFILE_ID_PATTERN.match(path)
        if profile_id_match:
            return "profile", profile_id_match

        lowered_path = path.lower()
        if lowered_path.startswith("music/playlist/"):
            return None, None
        if any(lowered_path.startswith(prefix) for prefix in self.RESERVED_COMMUNITY_PREFIXES):
            return None, None

        community_match = self.COMMUNITY_PATTERN.match(path)
        if community_match:
            return "profile", community_match

        return None, None
