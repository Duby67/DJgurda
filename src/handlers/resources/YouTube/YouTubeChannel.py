"""
Обработчик профилей/страниц каналов YouTube.
"""

import html
from typing import Any, Dict, Optional

from src.handlers.mixins import MetadataMixin, PhotoMixin
from .cookies import build_youtube_cookie_opts


class YouTubeChannel(PhotoMixin, MetadataMixin):
    """
    Миксин для извлечения метаданных канала YouTube.
    """

    @staticmethod
    def _first_non_empty(*values: Any) -> Optional[str]:
        """
        Возвращает первую непустую строку из набора значений.
        """
        for value in values:
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @staticmethod
    def _format_count(value: Any) -> Optional[str]:
        """
        Форматирует числовое значение для компактного отображения.
        """
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
        """
        Формирует мобильный caption для карточки канала.
        """
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

    def _extract_total_videos_count(self, info: Dict[str, Any]) -> Optional[str]:
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

    async def _process_youtube_channel(
        self,
        url: str,
        context: str,
        original_url: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Извлекает метаданные канала и возвращает профильную карточку.
        """
        ydl_opts = {
            "extract_flat": True,
            "extractor_args": {
                "youtube": {
                    "player_client": ["android", "web", "ios"],
                }
            },
        }
        ydl_opts.update(build_youtube_cookie_opts())

        info = await self._extract_metadata(url, ydl_opts)
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

        avatar_url = self._pick_thumbnail_url(
            info,
            candidate_keys=("channel_thumbnail", "thumbnail", "thumbnails"),
        )
        avatar_path = None
        if avatar_url:
            avatar_path = self._generate_unique_path(channel_id, suffix=".jpg")
            if not await self._download_photo(avatar_url, avatar_path, size_limit=self.photo_limit):
                avatar_path = None

        caption = self._build_channel_caption(
            channel_title=channel_title,
            channel_url=channel_url,
            description=description,
            subscriber_count=subscriber_count,
            video_count=video_count,
        )

        return {
            "type": "channel",
            "source_name": "YouTube",
            "file_path": avatar_path,
            "thumbnail_path": None,
            "title": channel_title,
            "uploader": channel_id,
            "original_url": original_url,
            "context": context,
            "caption_text": caption,
        }
