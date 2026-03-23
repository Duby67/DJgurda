"""
Процессор плейлистов YouTube.
"""

from __future__ import annotations

import html
from typing import Any, Optional
from urllib.parse import parse_qs, quote_plus, urlsplit

from src.handlers.contracts import ContentType, MediaResult

from .YouTubeDependencies import YouTubeMediaGatewayProtocol, YouTubeOptionsProviderProtocol


class YouTubePlaylist:
    """Процессор для preview-обработки YouTube playlist URL."""

    def __init__(
        self,
        *,
        media_gateway: YouTubeMediaGatewayProtocol,
        options_provider: YouTubeOptionsProviderProtocol,
    ) -> None:
        self._media_gateway = media_gateway
        self._options_provider = options_provider

    @staticmethod
    def _first_non_empty(*values: Any) -> Optional[str]:
        """Возвращает первую непустую строку из набора значений."""
        for value in values:
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @staticmethod
    def _format_count(value: Any) -> Optional[str]:
        """Форматирует числовое значение для компактного отображения."""
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return f"{value:,}"
        if isinstance(value, str) and value.isdigit():
            return f"{int(value):,}"
        return None

    @staticmethod
    def _extract_playlist_id(url: str) -> Optional[str]:
        """Извлекает playlist id из query-параметра `list`."""
        query = parse_qs(urlsplit(url).query)
        playlist_ids = query.get("list", [])
        for playlist_id in playlist_ids:
            if isinstance(playlist_id, str) and playlist_id.strip():
                return playlist_id.strip()
        return None

    @classmethod
    def _build_canonical_playlist_url(cls, url: str) -> str:
        """Строит канонический URL плейлиста по его `list` id."""
        playlist_id = cls._extract_playlist_id(url)
        if not playlist_id:
            return url
        return f"https://www.youtube.com/playlist?list={quote_plus(playlist_id)}"

    @staticmethod
    def _extract_preview_entries(info: dict[str, Any], limit: int = 5) -> list[dict[str, str]]:
        """Выбирает первые элементы плейлиста для компактного превью."""
        entries = info.get("entries")
        if not isinstance(entries, list):
            return []

        preview_items: list[dict[str, str]] = []
        for entry in entries[:limit]:
            if not isinstance(entry, dict):
                continue

            title = entry.get("title")
            if not isinstance(title, str) or not title.strip():
                title = "YouTube Video"

            uploader = entry.get("uploader") or entry.get("channel") or entry.get("channel_id")
            if not isinstance(uploader, str):
                uploader = ""

            preview_items.append(
                {
                    "title": title.strip(),
                    "uploader": uploader.strip(),
                }
            )

        return preview_items

    def _build_playlist_caption(
        self,
        *,
        playlist_title: str,
        playlist_url: str,
        owner: Optional[str],
        video_count: Optional[str],
        preview_entries: list[dict[str, str]],
    ) -> str:
        """Формирует mobile-first caption для карточки плейлиста."""
        safe_title = html.escape(playlist_title)
        safe_url = html.escape(playlist_url, quote=True)

        lines = [f'<a href="{safe_url}"><b>{safe_title}</b></a>']

        stats: list[str] = []
        if owner:
            stats.append(f"Автор: {html.escape(owner)}")
        if video_count:
            stats.append(f"🎬 Видео: {video_count}")

        if stats:
            lines.append("")
            lines.extend(stats)

        if preview_entries:
            lines.append("")
            lines.append("Первые видео:")
            for index, entry in enumerate(preview_entries, start=1):
                safe_entry_title = html.escape(entry["title"])
                uploader = entry["uploader"]
                if uploader:
                    lines.append(f"{index}. {html.escape(uploader)} - {safe_entry_title}")
                else:
                    lines.append(f"{index}. {safe_entry_title}")

        return "\n".join(lines)

    async def process(
        self,
        url: str,
        context: str,
        original_url: str,
    ) -> Optional[MediaResult]:
        """Извлекает метаданные плейлиста и возвращает preview `MediaResult`."""
        canonical_url = self._build_canonical_playlist_url(url)

        ydl_opts: dict[str, Any] = {
            "extract_flat": True,
            "playlistend": 5,
            "extractor_args": {
                "youtube": {
                    "player_client": ["android", "tv_embedded", "ios", "web"],
                }
            },
        }
        ydl_opts.update(self._options_provider.build_ytdlp_opts())

        info = await self._media_gateway.extract_metadata(canonical_url, ydl_opts)
        if not info:
            return None

        playlist_id = self._extract_playlist_id(canonical_url) or "unknown"
        playlist_title = self._first_non_empty(
            info.get("title"),
            info.get("playlist_title"),
            "YouTube Playlist",
        ) or "YouTube Playlist"
        owner = self._first_non_empty(
            info.get("uploader"),
            info.get("channel"),
            info.get("channel_id"),
        )
        video_count = self._format_count(
            info.get("playlist_count") or info.get("n_entries") or info.get("entry_count")
        )
        preview_entries = self._extract_preview_entries(info)
        caption = self._build_playlist_caption(
            playlist_title=playlist_title,
            playlist_url=canonical_url,
            owner=owner,
            video_count=video_count,
            preview_entries=preview_entries,
        )

        return MediaResult(
            content_type=ContentType.PLAYLIST,
            source_name="YouTube",
            original_url=original_url,
            context=context,
            title=playlist_title,
            uploader=owner or playlist_id,
            caption_text=caption,
        )
