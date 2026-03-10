"""
Процессор Instagram media_group (carousel-посты).
"""

from __future__ import annotations

import re
from typing import Any, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from src.handlers.contracts import AttachmentKind, AudioAttachment, ContentType, MediaAttachment, MediaResult

from .InstagramDependencies import InstagramMediaGatewayProtocol, InstagramOptionsProviderProtocol


class InstagramMediaGroup:
    """Процессор для обработки carousel-постов Instagram."""

    POST_ID_PATTERN = re.compile(r"/p/([A-Za-z0-9_-]+)")

    def __init__(
        self,
        *,
        media_gateway: InstagramMediaGatewayProtocol,
        options_provider: InstagramOptionsProviderProtocol,
    ) -> None:
        self._media_gateway = media_gateway
        self._options_provider = options_provider

    @staticmethod
    def normalize_media_group_url(url: str) -> str:
        """Убирает параметры, фиксирующие отдельный слайд карусели."""
        parts = urlsplit(url)
        filtered_items = [
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if key.lower() != "img_index"
        ]
        normalized_query = urlencode(filtered_items, doseq=True)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, normalized_query, parts.fragment))

    async def process(
        self,
        url: str,
        context: str,
        original_url: str,
    ) -> Optional[MediaResult]:
        """Скачивает медиа-карусель и формирует typed `MediaResult`."""
        normalized_url = self.normalize_media_group_url(url)
        post_match = self.POST_ID_PATTERN.search(url)
        post_id = post_match.group(1) if post_match else self._media_gateway.extract_video_id(url)

        ydl_opts: dict[str, Any] = {
            "format": "best[height<=1920][ext=mp4]/best[ext=jpg]/best",
            "ignoreerrors": True,
            "extract_flat": False,
            "noplaylist": False,
            "writethumbnail": False,
        }
        ydl_opts.update(self._options_provider.build_ytdlp_opts())

        media_list = await self._media_gateway.download_media_group(
            normalized_url,
            ydl_opts,
            group_id=post_id,
            size_limit=max(self._media_gateway.video_limit, self._media_gateway.photo_limit),
        )
        if not media_list:
            return None

        media_group = tuple(
            MediaAttachment(
                kind=AttachmentKind.PHOTO if item.get("type") == "photo" else AttachmentKind.VIDEO,
                file_path=item["file_path"],
            )
            for item in media_list
            if item.get("type") in {"photo", "video"} and item.get("file_path") is not None
        )
        if not media_group:
            return None

        audio_items = tuple(
            AudioAttachment(
                file_path=item["file_path"],
            )
            for item in media_list
            if item.get("type") == "audio" and item.get("file_path") is not None
        )

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

        # Для карусели используем title/uploader как fallback метаданные аудио.
        enriched_audios = tuple(
            AudioAttachment(
                file_path=item.file_path,
                title=title,
                performer=uploader,
            )
            for item in audio_items
        )

        return MediaResult(
            content_type=ContentType.MEDIA_GROUP,
            source_name="Instagram",
            original_url=original_url,
            context=context,
            title=title,
            uploader=uploader,
            media_group=media_group,
            audios=enriched_audios,
            audio=enriched_audios[0] if enriched_audios else None,
        )