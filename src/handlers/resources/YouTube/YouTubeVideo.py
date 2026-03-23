"""
Процессор обычного видео-контента YouTube.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

from typing import Any, Optional

from src.handlers.contracts import ContentType, MediaResult

from .YouTubeDependencies import YouTubeMediaGatewayProtocol, YouTubeOptionsProviderProtocol


class YouTubeVideo:
    """Процессор для скачивания и подготовки обычного YouTube видео."""

    def __init__(
        self,
        *,
        media_gateway: YouTubeMediaGatewayProtocol,
        options_provider: YouTubeOptionsProviderProtocol,
    ) -> None:
        self._media_gateway = media_gateway
        self._options_provider = options_provider

    @staticmethod
    def _extract_video_id(url: str) -> str:
        """Извлекает video id из watch/youtu.be/live/embed/v URL."""
        parts = urlsplit(url)
        host = parts.netloc.lower()
        path_parts = [part for part in parts.path.split("/") if part]
        query = parse_qs(parts.query)

        if host == "youtu.be" and path_parts:
            return path_parts[0]

        if "v" in query and query["v"]:
            return query["v"][0]

        if path_parts and path_parts[0].lower() in {"embed", "live", "v"} and len(path_parts) >= 2:
            return path_parts[1]

        if path_parts:
            return path_parts[-1]

        return "youtube_video"

    async def process(
        self,
        url: str,
        context: str,
        original_url: str,
    ) -> Optional[MediaResult]:
        """Скачивает видео и возвращает typed `MediaResult`."""
        video_id = self._extract_video_id(url)

        ydl_opts: dict[str, Any] = {
            "format": "best[height<=1920][ext=mp4]/best[height<=1920]/best",
            "merge_output_format": "mp4",
            "writethumbnail": True,
            "noplaylist": True,
            "extractor_args": {
                "youtube": {
                    "player_client": ["android", "tv_embedded", "ios", "web"],
                }
            },
        }
        ydl_opts.update(self._options_provider.build_ytdlp_opts())

        result = await self._media_gateway.download_video(
            url,
            ydl_opts,
            video_id=video_id,
            size_limit=self._media_gateway.video_limit,
        )
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
            source_name="YouTube",
            original_url=original_url,
            context=context,
            title=info.get("title", "YouTube Video"),
            uploader=info.get("uploader", info.get("channel", "Unknown")),
            main_file_path=file_path,
            thumbnail_path=result.get("thumbnail_path"),
        )
