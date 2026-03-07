"""
Обработчик профилей Instagram.
"""

import html
import logging
import re
from urllib.parse import quote
from typing import Any, Dict, Optional

import aiohttp

from src.handlers.mixins import MetadataMixin, PhotoMixin

logger = logging.getLogger(__name__)


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

    @staticmethod
    def _extract_username_from_url(url: str) -> Optional[str]:
        """
        Возвращает username из profile URL Instagram.
        """
        matched_profile = InstagramProfile.PROFILE_NAME_PATTERN.search(url)
        if not matched_profile:
            return None
        username = matched_profile.group(1).strip()
        return username or None

    @staticmethod
    def _build_canonical_profile_url(username: str) -> str:
        """
        Строит канонический URL профиля с завершающим `/`.
        """
        return f"https://www.instagram.com/{username}/"

    @staticmethod
    def _build_metadata_from_web_profile_user(
        user_payload: Dict[str, Any],
        username: str,
    ) -> Dict[str, Any]:
        """
        Приводит payload web_profile_info к формату полей, ожидаемых обработчиком.
        """
        biography = user_payload.get("biography")
        full_name = user_payload.get("full_name")
        profile_url = InstagramProfile._build_canonical_profile_url(username)
        followers_count = (
            (user_payload.get("edge_followed_by") or {}).get("count")
            if isinstance(user_payload.get("edge_followed_by"), dict)
            else None
        )
        posts_count = (
            (user_payload.get("edge_owner_to_timeline_media") or {}).get("count")
            if isinstance(user_payload.get("edge_owner_to_timeline_media"), dict)
            else None
        )
        avatar_url = (
            user_payload.get("profile_pic_url_hd")
            or user_payload.get("profile_pic_url")
        )

        return {
            "uploader_id": username,
            "uploader": username,
            "channel": full_name or username,
            "uploader_url": profile_url,
            "channel_url": profile_url,
            "webpage_url": profile_url,
            "description": biography,
            "channel_follower_count": followers_count,
            "media_count": posts_count,
            "thumbnail": avatar_url,
        }

    async def _extract_profile_via_web_api(self, username: str) -> Optional[Dict[str, Any]]:
        """
        Резервное получение данных профиля через web_profile_info endpoint.
        """
        api_url = (
            "https://i.instagram.com/api/v1/users/web_profile_info/"
            f"?username={quote(username)}"
        )
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "X-IG-App-ID": "936619743392459",
            "Referer": "https://www.instagram.com/",
            "Accept": "application/json",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    api_url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=12),
                ) as response:
                    if response.status != 200:
                        logger.warning(
                            "Instagram web_profile_info returned status %s for username=%s",
                            response.status,
                            username,
                        )
                        return None
                    payload = await response.json(content_type=None)
        except Exception:
            logger.exception("Failed to fetch Instagram web_profile_info for username=%s", username)
            return None

        data = payload.get("data") if isinstance(payload, dict) else None
        user_payload = data.get("user") if isinstance(data, dict) else None
        if not isinstance(user_payload, dict):
            logger.warning("Instagram web_profile_info payload has no user block for username=%s", username)
            return None

        return self._build_metadata_from_web_profile_user(user_payload, username)

    async def _process_instagram_profile(
        self,
        url: str,
        context: str,
        original_url: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Извлекает данные профиля Instagram и формирует карточку профиля.
        """
        matched_username = self._extract_username_from_url(url)
        if not matched_username:
            return None
        canonical_url = self._build_canonical_profile_url(matched_username)

        ydl_opts = {
            "extract_flat": True,
        }

        info = await self._extract_metadata(canonical_url, ydl_opts)
        if not info and canonical_url != url:
            # Резервный запуск на исходном URL, если канонический внезапно не сработал.
            info = await self._extract_metadata(url, ydl_opts)
        if not info:
            info = await self._extract_profile_via_web_api(matched_username)
        if not info:
            return None

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
            canonical_url,
        ) or canonical_url
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
