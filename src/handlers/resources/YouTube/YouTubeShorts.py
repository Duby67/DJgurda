"""
Процессор Shorts-контента YouTube.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from src.handlers.contracts import ContentType, MediaResult

from .YouTubeDependencies import YouTubeMediaGatewayProtocol, YouTubeOptionsProviderProtocol


class YouTubeShorts:
    """Процессор для скачивания и подготовки YouTube Shorts."""

    SHORTS_ID_PATTERN = re.compile(r"/shorts/([A-Za-z0-9_-]+)")

    def __init__(
        self,
        *,
        media_gateway: YouTubeMediaGatewayProtocol,
        options_provider: YouTubeOptionsProviderProtocol,
    ) -> None:
        self._media_gateway = media_gateway
        self._options_provider = options_provider

    async def process(
        self,
        url: str,
        context: str,
        original_url: str,
    ) -> Optional[MediaResult]:
        """Скачивает Shorts и возвращает typed `MediaResult`."""
        shorts_match = self.SHORTS_ID_PATTERN.search(url)
        shorts_id = shorts_match.group(1) if shorts_match else self._media_gateway.extract_video_id(url)

        ydl_opts: dict[str, Any] = {
            "format": "best[height<=1920][ext=mp4]/best[height<=1920]/best",
            "merge_output_format": "mp4",
            "writethumbnail": True,
            "noplaylist": True,
            "extractor_args": {
                "youtube": {
                    # Сначала мобильные/embedded-клиенты, чтобы снизить риск bot-check на web-клиенте.
                    "player_client": ["android", "tv_embedded", "ios", "web"],
                }
            },
        }
        ydl_opts.update(self._options_provider.build_ytdlp_opts())

        result = await self._media_gateway.download_video(url, ydl_opts, video_id=shorts_id)
        if not result:
            return None

        info = result.get("info") if isinstance(result, dict) else None
        if not isinstance(info, dict):
            info = {}

        file_path = result.get("file_path")
        if file_path is None:
            return None

        thumbnail_path = result.get("thumbnail_path")

        return MediaResult(
            content_type=ContentType.SHORTS,
            source_name="YouTube",
            original_url=original_url,
            context=context,
            title=info.get("title", "YouTube Shorts"),
            uploader=info.get("uploader", info.get("channel", "Unknown")),
            main_file_path=file_path,
            thumbnail_path=thumbnail_path,
        )