"""
Процессор видео-контента TikTok.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from src.handlers.contracts import ContentType, MediaResult

from .TikTokDependencies import TikTokMediaGatewayProtocol, TikTokOptionsProviderProtocol


class TikTokVideo:
    """Процессор для скачивания и подготовки TikTok видео."""

    VIDEO_ID_PATTERN = re.compile(r"/(\d+)[?/]?")

    def __init__(
        self,
        *,
        media_gateway: TikTokMediaGatewayProtocol,
        options_provider: TikTokOptionsProviderProtocol,
    ) -> None:
        self._media_gateway = media_gateway
        self._options_provider = options_provider

    async def process(
        self,
        url: str,
        context: str,
        original_url: str,
    ) -> Optional[MediaResult]:
        """Скачивает видео и возвращает typed `MediaResult`."""
        video_id_match = self.VIDEO_ID_PATTERN.search(url)
        video_id = (
            video_id_match.group(1)
            if video_id_match
            else self._media_gateway.extract_video_id(url)
        )

        ydl_opts: dict[str, Any] = {
            # Для части TikTok-постов метаданные форматов неполные
            # (например, без height/ext), поэтому оставляем мягкий fallback до `best`.
            "format": "best[height<=1080][ext=mp4]/best[height<=1080]/best[ext=mp4]/best",
            "writethumbnail": True,
        }
        ydl_opts.update(self._options_provider.build_ytdlp_opts())

        result = await self._media_gateway.download_video(url, ydl_opts, video_id=video_id)
        if not result:
            return None

        info = result.get("info") if isinstance(result, dict) else None
        if not isinstance(info, dict):
            info = {}

        file_path = result.get("file_path")
        if file_path is None:
            return None

        return MediaResult(
            content_type=ContentType.VIDEO,
            source_name="TikTok",
            original_url=original_url,
            context=context,
            title=info.get("title", "TikTok Video"),
            uploader=info.get("uploader", info.get("channel", "Unknown")),
            main_file_path=file_path,
            thumbnail_path=result.get("thumbnail_path"),
        )