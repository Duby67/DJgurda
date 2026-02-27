import re
import logging

from typing import Optional, Dict, Any

from src.services.base import BaseHandler
from src.services.mixins import VideoMixin

logger = logging.getLogger(__name__)

class InstagramHandler(BaseHandler, VideoMixin):
    PATTERN = re.compile(r'https?://(?:www\.)?instagram\.com/(?:reel|p|tv)/\S+')

    @property
    def pattern(self) -> re.Pattern:
        return self.PATTERN

    @property
    def source_name(self) -> str:
        return "Instagram"

    async def process(self, url: str, context: str) -> Optional[Dict[str, Any]]:
        shortcode_match = re.search(r'/(reel|p|tv)/([a-zA-Z0-9_-]+)', url)
        video_id = shortcode_match.group(2) if shortcode_match else self._extract_video_id(url)

        ydl_opts = {
            'format': 'best[ext=mp4]/best',
            'writethumbnail': True,
        }
        result = await self._download_video(url, ydl_opts, video_id=video_id)
        if not result:
            return None

        info = result['info']
        return {
            'type': 'video',
            'source_name': self.source_name,
            'file_path': result['file_path'],
            'thumbnail_path': result['thumbnail_path'],
            'title': info.get('title', 'Unknown'),
            'uploader': info.get('uploader', info.get('channel', 'Unknown')),
            'original_url': url,
            'context': context,
        }