"""
Обработчик Instagram Stories.
"""

import re
from typing import Any, Dict, Optional

from src.handlers.mixins import MediaGroupMixin


class InstagramStories(MediaGroupMixin):
    """
    Миксин для обработки stories-ссылок Instagram.
    """

    STORY_ID_PATTERN = re.compile(r"/stories/[^/]+/(\d+)")
    STORY_USER_PATTERN = re.compile(r"/stories/([^/]+)/")

    async def _process_instagram_stories(
        self,
        url: str,
        context: str,
        original_url: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Скачивает story и возвращает результат с явным типом `stories`.
        """
        story_id_match = self.STORY_ID_PATTERN.search(url)
        story_id = story_id_match.group(1) if story_id_match else self._extract_video_id(url)

        ydl_opts = {
            "format": "best[height<=1920][ext=mp4]/best[ext=jpg]/best",
            "ignoreerrors": True,
            "extract_flat": False,
            "noplaylist": True,
            "writethumbnail": False,
        }
        media_list = await self._download_media_group(
            url,
            ydl_opts,
            group_id=story_id,
            size_limit=max(self.video_limit, self.photo_limit),
        )
        if not media_list:
            return None

        media_items = [item for item in media_list if item.get("type") in {"photo", "video"}]
        if not media_items:
            return None

        primary_item = media_items[0]
        first_info = primary_item.get("info")
        if not isinstance(first_info, dict):
            first_info = {}

        title = first_info.get("title") or "Instagram Story"
        uploader = (
            first_info.get("uploader")
            or first_info.get("channel")
            or first_info.get("uploader_id")
        )
        if not uploader:
            user_match = self.STORY_USER_PATTERN.search(url)
            uploader = user_match.group(1) if user_match else "Unknown"

        return {
            "type": "stories",
            "source_name": "Instagram",
            "story_media_type": primary_item["type"],
            "file_path": primary_item["file_path"],
            "thumbnail_path": None,
            "files": [
                {"file_path": item["file_path"], "type": item["type"]}
                for item in media_items
            ],
            "title": title,
            "uploader": uploader,
            "original_url": original_url,
            "context": context,
        }

