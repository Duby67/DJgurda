"""
Обработчик видео-контента COUB.
"""

import logging
import re
from typing import Any, Dict, Optional

from src.handlers.mixins import VideoMixin

logger = logging.getLogger(__name__)


class CoubVideo(VideoMixin):
    """
    Миксин для обработки видео из COUB.
    """

    COUB_ID_PATTERN = re.compile(r"/view/([A-Za-z0-9]+)")

    async def _process_coub_video(
        self,
        url: str,
        context: str,
        original_url: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Скачивает COUB-видео и возвращает структуру для дальнейшей отправки.
        """
        coub_match = self.COUB_ID_PATTERN.search(url)
        coub_id = coub_match.group(1) if coub_match else self._extract_video_id(url)

        # Берем исходный mp4, чтобы получить максимально совместимый вариант для Telegram.
        ydl_opts = {
            "format": "mp4/best[ext=mp4]/best",
            "writethumbnail": True,
            "noplaylist": True,
            "merge_output_format": "mp4",
        }

        result = await self._download_video(url, ydl_opts, video_id=coub_id)
        if not result:
            return None

        info = result["info"]
        return {
            "type": "video",
            "source_name": "COUB",
            "file_path": result["file_path"],
            "thumbnail_path": result["thumbnail_path"],
            "title": info.get("title", "COUB Video"),
            "uploader": info.get("uploader", info.get("channel", "Unknown")),
            "original_url": original_url,
            "context": context,
        }
