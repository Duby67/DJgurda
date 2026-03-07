"""
Обработчик Instagram media_group (carousel-посты).
"""

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from typing import Any, Dict, Optional

from src.handlers.mixins import MediaGroupMixin
from .cookies import build_instagram_cookie_opts


class InstagramMediaGroup(MediaGroupMixin):
    """
    Миксин для обработки carousel-постов Instagram.
    """

    POST_ID_PATTERN = re.compile(r"/p/([A-Za-z0-9_-]+)")

    @staticmethod
    def _normalize_media_group_url(url: str) -> str:
        """
        Убирает параметры, которые фиксируют отдельный слайд и мешают получить всю карусель.
        """
        parts = urlsplit(url)
        filtered_items = [
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if key.lower() != "img_index"
        ]
        normalized_query = urlencode(filtered_items, doseq=True)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, normalized_query, parts.fragment))

    async def _process_instagram_media_group(
        self,
        url: str,
        context: str,
        original_url: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Скачивает медиа-карусель и формирует ответ в формате media_group.
        """
        normalized_url = self._normalize_media_group_url(url)
        post_match = self.POST_ID_PATTERN.search(url)
        post_id = post_match.group(1) if post_match else self._extract_video_id(url)

        ydl_opts = {
            "format": "best[height<=1920][ext=mp4]/best[ext=jpg]/best",
            "ignoreerrors": True,
            "extract_flat": False,
            "noplaylist": False,
            "writethumbnail": False,
        }
        ydl_opts.update(build_instagram_cookie_opts())
        media_list = await self._download_media_group(
            normalized_url,
            ydl_opts,
            group_id=post_id,
            size_limit=max(self.video_limit, self.photo_limit),
        )
        if not media_list:
            return None

        files = [
            {"file_path": item["file_path"], "type": item["type"]}
            for item in media_list
            if item.get("type") in {"photo", "video"}
        ]
        if not files:
            return None

        audio_files = [
            {"file_path": item["file_path"]}
            for item in media_list
            if item.get("type") == "audio"
        ]

        first_info = media_list[0].get("info")
        if not isinstance(first_info, dict):
            first_info = {}

        title = first_info.get("title") or first_info.get("description") or "Instagram Post"
        uploader = (
            first_info.get("uploader")
            or first_info.get("channel")
            or first_info.get("uploader_id")
            or "Unknown"
        )

        result = {
            "type": "media_group",
            "source_name": "Instagram",
            "files": files,
            "title": title,
            "uploader": uploader,
            "original_url": original_url,
            "context": context,
        }

        if audio_files:
            # Поддерживаем несколько дополнительных аудиофайлов для карусели.
            result["audios"] = [
                {
                    "file_path": item["file_path"],
                    "title": title,
                    "performer": uploader,
                }
                for item in audio_files
            ]

        return result
