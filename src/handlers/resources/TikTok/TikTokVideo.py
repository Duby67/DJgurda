"""
Обработчик видео контента TikTok.
"""

import re
import logging
from typing import Optional, Dict, Any

from src.handlers.mixins import VideoMixin

logger = logging.getLogger(__name__)

class TikTokVideo(VideoMixin):
    """
    Миксин для обработки видео с TikTok.
    """
    
    async def _process_tiktok_video(
        self,
        url: str,
        context: str,
        resolved_url: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Обрабатывает видео с TikTok.
        
        Аргументы:
            url: URL видео
            context: Контекст сообщения
            resolved_url: Разрешенный URL
            
        Возвращает:
            Словарь с информацией о видео или None при ошибке
        """
        target_url = resolved_url or url
        
        # Извлекаем ID видео из URL
        video_id_match = re.search(r'/(\d+)[?/]?', target_url)
        video_id = video_id_match.group(1) if video_id_match else self._extract_video_id(target_url)

        # Опции для yt-dlp
        ydl_opts = {
            # Для части TikTok-постов метаданные форматов неполные
            # (например, без height/ext), поэтому оставляем мягкий fallback до `best`.
            'format': 'best[height<=1080][ext=mp4]/best[height<=1080]/best[ext=mp4]/best',
            'writethumbnail': True,
        }
        ydl_opts.update(self._build_tiktok_cookie_opts())

        result = await self._download_video(target_url, ydl_opts, video_id=video_id)
        if not result:
            return None

        info = result['info']
        return {
            'type': 'video',
            'source_name': 'TikTok',
            'file_path': result['file_path'],
            'thumbnail_path': result['thumbnail_path'],
            'title': info.get('title', 'TikTok Video'),
            'uploader': info.get('uploader', info.get('channel', 'Unknown')),
            'original_url': url,
            'context': context,
        }
