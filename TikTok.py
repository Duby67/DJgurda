import re
import asyncio
import logging
from pathlib import Path
from typing import Optional, Dict, Any
import yt_dlp

from base_handler import BaseHandler

logger = logging.getLogger(__name__)

class TikTokHandler(BaseHandler):
    PATTERN = re.compile(
        r'https?://(?:www\.|vm\.)?tiktok\.com/(?:@[\w.-]+/video/\d+|[\d]+|[a-zA-Z0-9_-]+)'
    )
    TEMP_DIR = Path("temp_files/TikTok")
    TEMP_DIR.mkdir(parents=True, exist_ok=True)

    @property
    def pattern(self) -> re.Pattern:
        return self.PATTERN

    @property
    def source_name(self) -> str:
        return "TikTok"

    async def process(self, url: str, context: str) -> Optional[Dict[str, Any]]:
        try:
            # Генерируем имя файла на основе части ссылки
            video_id_match = re.search(r'(\d+)|([a-zA-Z0-9_-]+)$', url)
            video_id = video_id_match.group(0) if video_id_match else "unknown"
            file_path = self.TEMP_DIR / f"{video_id}.mp4"
            thumb_path = self.TEMP_DIR / f"{video_id}.jpg"

            ydl_opts = {
                'outtmpl': str(file_path),
                'format': 'best[ext=mp4]/best',
                'writethumbnail': True,
                'quiet': True,
                'no_warnings': True,
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }

            loop = asyncio.get_event_loop()
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=True))
                if not info:
                    logger.error("Не удалось получить информацию о видео TikTok")
                    return None

                if not file_path.exists():
                    logger.error(f"Файл не найден: {file_path}")
                    return None

                # Проверка размера (Telegram ограничение 50 МБ)
                file_size = file_path.stat().st_size
                if file_size > 50 * 1024 * 1024:
                    logger.warning(f"Видео слишком большое ({file_size} байт). Удаляем.")
                    file_path.unlink()
                    return None

                # Поиск миниатюры
                possible_thumb = file_path.with_suffix('.jpg')
                if possible_thumb.exists():
                    thumb_path = possible_thumb
                else:
                    thumb_path = None

                return {
                    'type': 'video',
                    'source_name': self.source_name,
                    'file_path': file_path,
                    'thumbnail_path': thumb_path,
                    'title': info.get('title', 'Unknown'),
                    'uploader': info.get('uploader', info.get('channel', 'Unknown')),
                    'original_url': url,
                    'context': context,
                }
        except Exception as e:
            logger.exception(f"Ошибка при скачивании видео TikTok: {e}")
            return None

    def cleanup(self, file_info: Dict[str, Any]) -> None:
        """Удаляет временные файлы."""
        if file_info.get('file_path'):
            try:
                file_info['file_path'].unlink()
            except Exception as e:
                logger.error(f"Ошибка удаления {file_info['file_path']}: {e}")
        if file_info.get('thumbnail_path'):
            try:
                file_info['thumbnail_path'].unlink()
            except Exception as e:
                logger.error(f"Ошибка удаления {file_info['thumbnail_path']}: {e}")