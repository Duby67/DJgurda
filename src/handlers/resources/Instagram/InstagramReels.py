"""
Обработчик Reels-контента Instagram.
"""

import re
from typing import Any, Dict, Optional

from src.handlers.mixins import VideoMixin


class InstagramReels(VideoMixin):
    """
    Миксин для скачивания Reels-видео.
    """

    REELS_ID_PATTERN = re.compile(r"/(?:reel|reels)/([A-Za-z0-9_-]+)")

    async def _process_instagram_reels(
        self,
        url: str,
        context: str,
        original_url: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Скачивает Reels и возвращает результат для общего pipeline.
        """
        reels_match = self.REELS_ID_PATTERN.search(url)
        reels_id = reels_match.group(1) if reels_match else self._extract_video_id(url)

        ydl_opts = {
            "format": "best[height<=1920][ext=mp4]/best[ext=mp4]/best",
            "merge_output_format": "mp4",
            "writethumbnail": True,
            "noplaylist": True,
        }
        ydl_opts.update(self._build_instagram_cookie_opts())

        result = await self._download_video(url, ydl_opts, video_id=reels_id)
        if not result:
            return None

        info = result["info"]
        return {
            "type": "reels",
            "source_name": "Instagram",
            "file_path": result["file_path"],
            "thumbnail_path": result["thumbnail_path"],
            "title": info.get("title", "Instagram Reels"),
            "uploader": info.get("uploader", info.get("channel", "Unknown")),
            "original_url": original_url,
            "context": context,
        }
