"""
Обработчик профилей Instagram.
"""

import html
import re
from typing import Any, Dict, Optional

from src.handlers.mixins import MetadataMixin, PhotoMixin


class InstagramProfile(PhotoMixin, MetadataMixin):
    """
    Миксин для извлечения данных профиля Instagram.
    """

    PROFILE_NAME_PATTERN = re.compile(r"https?://(?:www\.|m\.)?instagram\.com/([^/?#]+)/?")

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
        Форматирует счетчики (подписчики, публикации) для caption.
        """
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return f"{value:,}"
        if isinstance(value, str) and value.isdigit():
            return f"{int(value):,}"
        return None

    def _build_profile_caption(
        self,
        display_name: str,
        profile_url: str,
        description: Optional[str],
        followers: Optional[str],
        posts: Optional[str],
    ) -> str:
        """
        Формирует профильный caption в mobile-first стиле.
        """
        safe_name = html.escape(display_name)
        safe_url = html.escape(profile_url, quote=True)

        lines = [f'<a href="{safe_url}"><b>{safe_name}</b></a>']

        if description:
            normalized_description = " ".join(description.split())
            if len(normalized_description) > 260:
                normalized_description = normalized_description[:260].rstrip() + "..."
            lines.append(f"<i>{html.escape(normalized_description)}</i>")

        stats = []
        if followers:
            stats.append(f"👥 Подписчиков: {followers}")
        if posts:
            stats.append(f"🗂 Публикаций: {posts}")

        if stats:
            lines.append("")
            lines.extend(stats)

        return "\n".join(lines)

    async def _process_instagram_profile(
        self,
        url: str,
        context: str,
        original_url: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Извлекает данные профиля Instagram и формирует карточку профиля.
        """
        ydl_opts = {
            "extract_flat": True,
        }
        info = await self._extract_metadata(url, ydl_opts)
        if not info:
            return None

        matched_profile = self.PROFILE_NAME_PATTERN.search(url)
        matched_username = self._first_non_empty(
            matched_profile.group(1) if matched_profile else None
        )
        username = self._first_non_empty(
            info.get("uploader_id"),
            info.get("uploader"),
            matched_username,
        ) or "unknown"
        display_name = self._first_non_empty(
            info.get("channel"),
            info.get("uploader"),
            username,
        ) or "Instagram Profile"
        profile_url = self._first_non_empty(
            info.get("uploader_url"),
            info.get("channel_url"),
            info.get("webpage_url"),
            url,
        ) or url
        description = self._first_non_empty(info.get("description"))

        followers = self._format_count(
            info.get("channel_follower_count") or info.get("follower_count")
        )
        posts = self._format_count(
            info.get("playlist_count")
            or info.get("channel_video_count")
            or info.get("media_count")
        )

        avatar_url = self._pick_thumbnail_url(
            info,
            candidate_keys=("thumbnail", "thumbnails", "channel_thumbnail"),
        )
        avatar_path = None
        if avatar_url:
            avatar_path = self._generate_unique_path(username, suffix=".jpg")
            if not await self._download_photo(avatar_url, avatar_path, size_limit=self.photo_limit):
                avatar_path = None

        caption = self._build_profile_caption(
            display_name=display_name,
            profile_url=profile_url,
            description=description,
            followers=followers,
            posts=posts,
        )

        return {
            "type": "profile",
            "source_name": "Instagram",
            "file_path": avatar_path,
            "thumbnail_path": None,
            "title": display_name,
            "uploader": username,
            "original_url": original_url,
            "context": context,
            "caption_text": caption,
        }
