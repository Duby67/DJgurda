"""
Процессор профилей/страниц каналов YouTube.
"""

from __future__ import annotations

import html
from typing import Any, Optional
from urllib.parse import urlsplit, urlunsplit

from src.handlers.contracts import ContentType, MediaResult

from .YouTubeDependencies import YouTubeMediaGatewayProtocol, YouTubeOptionsProviderProtocol


class YouTubeChannel:
    """Процессор метаданных и карточки канала YouTube."""

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

    def _build_channel_caption(
        self,
        channel_title: str,
        channel_url: str,
        description: Optional[str],
        subscriber_count: Optional[str],
        video_count: Optional[str],
    ) -> str:
        """Формирует mobile-first caption для карточки канала."""
        safe_title = html.escape(channel_title)
        safe_url = html.escape(channel_url, quote=True)

        lines = [f'<a href="{safe_url}"><b>{safe_title}</b></a>']

        if description:
            normalized_description = " ".join(description.split())
            if len(normalized_description) > 260:
                normalized_description = normalized_description[:260].rstrip() + "..."
            lines.append(f"<i>{html.escape(normalized_description)}</i>")

        stats = []
        if subscriber_count:
            stats.append(f"👥 Подписчиков: {subscriber_count}")
        if video_count:
            stats.append(f"🎬 Видео: {video_count}")

        if stats:
            lines.append("")
            lines.extend(stats)

        return "\n".join(lines)

    def _extract_total_videos_count(self, info: dict[str, Any]) -> Optional[str]:
        """
        Возвращает общее количество видео на канале.

        Приоритет:
        1) channel_video_count / video_count (общее число видео)
        2) playlist_count (резервный вариант, может быть неточным)
        """
        primary_count = self._format_count(
            info.get("channel_video_count") or info.get("video_count")
        )
        if primary_count:
            return primary_count

        return self._format_count(info.get("playlist_count"))

    def _build_videos_tab_url(self, channel_url: str) -> str:
        """Возвращает URL вкладки `/videos` для канала."""
        parts = urlsplit(channel_url)
        path_parts = [part for part in parts.path.split("/") if part]
        if not path_parts:
            return channel_url

        tab_names = {"videos", "featured", "streams", "shorts", "playlists", "community", "about"}
        if path_parts[-1].lower() in tab_names:
            path_parts[-1] = "videos"
        else:
            path_parts.append("videos")

        videos_path = "/" + "/".join(path_parts)
        return urlunsplit((parts.scheme, parts.netloc, videos_path, "", ""))

    async def _extract_channel_metadata(
        self,
        channel_url: str,
        ydl_opts: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        """Извлекает метаданные канала с приоритетом данных из вкладки `/videos`."""
        videos_url = self._build_videos_tab_url(channel_url)
        videos_info = await self._media_gateway.extract_metadata(videos_url, ydl_opts)

        if videos_url == channel_url:
            return videos_info

        base_info = await self._media_gateway.extract_metadata(channel_url, ydl_opts)
        if not videos_info and not base_info:
            return None
        if videos_info and not base_info:
            return videos_info
        if base_info and not videos_info:
            return base_info

        merged_info = dict(base_info or {})
        for key in ("channel_video_count", "video_count", "playlist_count"):
            value = videos_info.get(key) if isinstance(videos_info, dict) else None
            if value not in (None, "", 0, "0"):
                merged_info[key] = value
        return merged_info

    async def process(
        self,
        url: str,
        context: str,
        original_url: str,
    ) -> Optional[MediaResult]:
        """Извлекает данные канала и возвращает typed `MediaResult`."""
        ydl_opts: dict[str, Any] = {
            "extract_flat": True,
            "extractor_args": {
                "youtube": {
                    "player_client": ["android", "tv_embedded", "ios", "web"],
                }
            },
        }
        ydl_opts.update(self._options_provider.build_ytdlp_opts())

        info = await self._extract_channel_metadata(url, ydl_opts)
        if not info:
            return None

        channel_title = self._first_non_empty(
            info.get("channel"),
            info.get("uploader"),
            info.get("title"),
        ) or "YouTube Channel"
        channel_id = self._first_non_empty(
            info.get("channel_id"),
            info.get("uploader_id"),
            info.get("id"),
        ) or "unknown"
        channel_url = self._first_non_empty(
            info.get("channel_url"),
            info.get("uploader_url"),
            info.get("webpage_url"),
            url,
        ) or url
        description = self._first_non_empty(info.get("description"))

        subscriber_count = self._format_count(
            info.get("channel_follower_count") or info.get("follower_count")
        )
        video_count = self._extract_total_videos_count(info)

        avatar_url = self._media_gateway.pick_thumbnail_url(
            info,
            candidate_keys=("channel_thumbnail", "thumbnail", "thumbnails"),
        )
        avatar_path = None
        if avatar_url:
            avatar_path = self._media_gateway.generate_unique_path(channel_id, suffix=".jpg")
            if not await self._media_gateway.download_photo(
                avatar_url,
                avatar_path,
                size_limit=self._media_gateway.photo_limit,
            ):
                avatar_path = None

        caption = self._build_channel_caption(
            channel_title=channel_title,
            channel_url=channel_url,
            description=description,
            subscriber_count=subscriber_count,
            video_count=video_count,
        )

        return MediaResult(
            content_type=ContentType.CHANNEL,
            source_name="YouTube",
            original_url=original_url,
            context=context,
            main_file_path=avatar_path,
            thumbnail_path=None,
            title=channel_title,
            uploader=channel_id,
            caption_text=caption,
        )