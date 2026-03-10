"""
Процессор Instagram Stories.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from src.handlers.contracts import AttachmentKind, ContentType, MediaAttachment, MediaResult

from .InstagramDependencies import InstagramMediaGatewayProtocol, InstagramOptionsProviderProtocol

logger = logging.getLogger(__name__)


class InstagramStories:
    """Процессор для обработки stories-ссылок Instagram."""

    STORY_ID_PATTERN = re.compile(r"/stories/[^/]+/(\d+)")
    STORY_USER_PATTERN = re.compile(r"/stories/([^/]+)/")

    def __init__(
        self,
        *,
        media_gateway: InstagramMediaGatewayProtocol,
        options_provider: InstagramOptionsProviderProtocol,
    ) -> None:
        self._media_gateway = media_gateway
        self._options_provider = options_provider

    async def process(
        self,
        url: str,
        context: str,
        original_url: str,
    ) -> Optional[MediaResult]:
        """Скачивает story и возвращает typed `MediaResult`."""
        story_id_match = self.STORY_ID_PATTERN.search(url)
        story_id = story_id_match.group(1) if story_id_match else self._media_gateway.extract_video_id(url)

        ydl_opts: dict[str, Any] = {
            "format": "best[height<=1920][ext=mp4]/best[ext=jpg]/best",
            "ignoreerrors": True,
            "extract_flat": False,
            "noplaylist": True,
            "writethumbnail": False,
        }
        ydl_opts.update(self._options_provider.build_ytdlp_opts())

        media_list = await self._media_gateway.download_media_group(
            url,
            ydl_opts,
            group_id=story_id,
            size_limit=max(self._media_gateway.video_limit, self._media_gateway.photo_limit),
        )
        if not media_list:
            logger.warning(
                "Failed to load Instagram stories %s. This content may require valid Instagram cookies.",
                url,
            )
            return None

        media_items = [item for item in media_list if item.get("type") in {"photo", "video"}]
        if not media_items:
            return None

        primary_item = media_items[0]
        first_info = primary_item.get("info")
        if not isinstance(first_info, dict):
            first_info = {}

        title = first_info.get("title") or "Instagram Story"
        uploader = first_info.get("uploader") or first_info.get("channel") or first_info.get("uploader_id")
        if not uploader:
            user_match = self.STORY_USER_PATTERN.search(url)
            uploader = user_match.group(1) if user_match else "Unknown"

        primary_type = str(primary_item.get("type"))
        story_media_kind = AttachmentKind.PHOTO if primary_type == "photo" else AttachmentKind.VIDEO

        main_file_path = primary_item.get("file_path")
        if main_file_path is None:
            return None

        return MediaResult(
            content_type=ContentType.STORIES,
            source_name="Instagram",
            original_url=original_url,
            context=context,
            title=title,
            uploader=uploader,
            main_file_path=main_file_path,
            thumbnail_path=None,
            story_media_kind=story_media_kind,
            media_group=tuple(
                MediaAttachment(
                    kind=AttachmentKind.PHOTO if item.get("type") == "photo" else AttachmentKind.VIDEO,
                    file_path=item["file_path"],
                )
                for item in media_items
                if item.get("file_path") is not None and item.get("type") in {"photo", "video"}
            ),
        )