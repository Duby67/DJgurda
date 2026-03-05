import re
import logging

from typing import Optional, Dict, Any

from src.handlers.mixins import VideoMixin

logger = logging.getLogger(__name__)

class TikTokVideo(VideoMixin):
    async def _process_tiktok_video(
        self,
        url: str,
        context: str,
        resolved_url: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        target_url = resolved_url or url
        video_id_match = re.search(r'/(\d+)[?/]?', target_url)
        video_id = video_id_match.group(1) if video_id_match else self._extract_video_id(target_url)

        ydl_opts = {
            'format': 'best[height<=1080][ext=mp4]/best[height<=1080]',
            'writethumbnail': True,
        }

        result = await self._download_video(target_url, ydl_opts, video_id=video_id)
        if not result:
            return None

        info = result['info']
        return {
            'type': 'video',
            'source_name': 'TikTok',
            'file_path': result['file_path'],
            'thumbnail_path': result['thumbnail_path'],
            'title': info.get('title', 'Unknown'),
            'uploader': info.get('uploader', info.get('channel', 'Unknown')),
            'original_url': url,
            'context': context,
        }