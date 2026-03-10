"""
Процессор Reels-контента Instagram.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from src.handlers.contracts import ContentType, MediaResult

from .InstagramDependencies import InstagramMediaGatewayProtocol, InstagramOptionsProviderProtocol


class InstagramReels:
    """Процессор для скачивания Reels-видео."""

    REELS_ID_PATTERN = re.compile(r"/(?:reel|reels)/([A-Za-z0-9_-]+)")

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
        """Скачивает Reels и возвращает typed `MediaResult`."""
        reels_match = self.REELS_ID_PATTERN.search(url)
        reels_id = reels_match.group(1) if reels_match else self._media_gateway.extract_video_id(url)

        ydl_opts: dict[str, Any] = {
            "format": "best[height<=1920][ext=mp4]/best[ext=mp4]/best",
            "merge_output_format": "mp4",
            "writethumbnail": True,
            "noplaylist": True,
        }
        ydl_opts.update(self._options_provider.build_ytdlp_opts())

        result = await self._media_gateway.download_video(url, ydl_opts, video_id=reels_id)
        if not result:
            return None

        info = result.get("info") if isinstance(result, dict) else None
        if not isinstance(info, dict):
            info = {}

        file_path = result.get("file_path")
        if file_path is None:
            return None

        return MediaResult(
            content_type=ContentType.REELS,
            source_name="Instagram",
            original_url=original_url,
            context=context,
            title=info.get("title", "Instagram Reels"),
            uploader=info.get("uploader", info.get("channel", "Unknown")),
            main_file_path=file_path,
            thumbnail_path=result.get("thumbnail_path"),
        )