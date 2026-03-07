"""
Обработчик Shorts-контента YouTube.
"""

import re
from typing import Any, Dict, Optional

from src.handlers.mixins import VideoMixin
from .cookies import build_youtube_cookie_opts


class YouTubeShorts(VideoMixin):
    """
    Миксин для скачивания и подготовки YouTube Shorts.
    """

    SHORTS_ID_PATTERN = re.compile(r"/shorts/([A-Za-z0-9_-]+)")

    async def _process_youtube_shorts(
        self,
        url: str,
        context: str,
        original_url: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Скачивает Shorts и возвращает файл + метаданные для общего pipeline.
        """
        shorts_match = self.SHORTS_ID_PATTERN.search(url)
        shorts_id = shorts_match.group(1) if shorts_match else self._extract_video_id(url)

        ydl_opts = {
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
        ydl_opts.update(build_youtube_cookie_opts())
        result = await self._download_video(url, ydl_opts, video_id=shorts_id)
        if not result:
            return None

        info = result["info"]
        return {
            "type": "shorts",
            "source_name": "YouTube",
            "file_path": result["file_path"],
            "thumbnail_path": result["thumbnail_path"],
            "title": info.get("title", "YouTube Shorts"),
            "uploader": info.get("uploader", info.get("channel", "Unknown")),
            "original_url": original_url,
            "context": context,
        }
