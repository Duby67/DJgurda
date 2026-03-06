"""Модуль `YouTube`."""
import re

from typing import Optional, Dict, Any

from src.handlers.base import BaseHandler
from src.handlers.mixins import VideoMixin

class YouTubeHandler(BaseHandler, VideoMixin):
    """Класс `YouTubeHandler`."""
    PATTERN = re.compile(
    r'https?://(?:www\.|m\.)?(?:youtube\.com/(?:watch\?v=|shorts/|embed/)|youtu\.be/)\S+'
    )

    @property
    def pattern(self) -> re.Pattern:
        """Функция `pattern`."""
        return self.PATTERN

    @property
    def source_name(self) -> str:
        """Функция `source_name`."""
        return "YouTube"

    async def process(self, url: str, context: str, resolved_url: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Функция `process`."""
        target_url = resolved_url or url
        ydl_opts = {
            'format': 'bestvideo+bestaudio/best',
            'extractor_args': {'youtube': {'player_client': ['android', 'web', 'ios']}},
            'writethumbnail': True,
        }
        result = await self._download_video(target_url, ydl_opts)
        if not result:
            return None

        info = result['info']
        return {
            'type': 'video',
            'source_name': self.source_name,
            'file_path': result['file_path'],
            'thumbnail_path': result['thumbnail_path'],
            'title': info.get('title', 'Unknown'),
            'uploader': info.get('uploader', 'Unknown'),
            'original_url': url,
            'context': context,
        }
