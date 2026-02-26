import re
import uuid
import yt_dlp
import asyncio
import logging

from typing import Optional, Dict, Any
from src.services.base import BaseHandler
from src.config import PROJECT_TEMP_DIR

logger = logging.getLogger(__name__)

class InstagramReelsHandler(BaseHandler):
    PATTERN = re.compile(r'https?://(?:www\.)?instagram\.com/(?:reel|p|tv)/\S+')
    TEMP_DIR = PROJECT_TEMP_DIR / "Instagram"
    TEMP_DIR.mkdir(parents=True, exist_ok=True)

    @property
    def pattern(self) -> re.Pattern:
        return self.PATTERN

    @property
    def source_name(self) -> str:
        return "Instagram Reels"

    async def process(self, url: str, context: str) -> Optional[Dict[str, Any]]:
        file_path = None
        thumb_path = None
        try:
            shortcode_match = re.search(r'/(reel|p|tv)/([a-zA-Z0-9_-]+)', url)
            if not shortcode_match:
                logger.error("Не удалось извлечь код Instagram")
                return None
            shortcode = shortcode_match.group(2)
            unique_id = f"{shortcode}_{uuid.uuid4().hex[:8]}"
            file_path = self.TEMP_DIR / f"{unique_id}.mp4"
            thumb_path = self.TEMP_DIR / f"{unique_id}.jpg"

            ydl_opts = {
                'outtmpl': str(file_path.with_suffix('')),
                'format': 'best[ext=mp4]/best',
                'writethumbnail': True,
                'quiet': True,
                'no_warnings': True,
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await asyncio.to_thread(ydl.extract_info, url, download=True)
                if not info:
                    logger.error("Не удалось получить информацию о видео Instagram")
                    return None

                possible_video = file_path.with_suffix('.mp4')
                if not possible_video.exists():
                    for f in self.TEMP_DIR.glob(f"{unique_id}.*"):
                        if f.suffix in ['.mp4', '.mov']:
                            possible_video = f
                            break
                    else:
                        logger.error(f"Файл не найден: {file_path}")
                        return None
                file_path = possible_video

                file_size = file_path.stat().st_size
                if file_size > 50 * 1024 * 1024:
                    logger.warning(f"Видео слишком большое ({file_size} байт). Удаляем.")
                    file_path.unlink()
                    return None

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
            logger.exception(f"Ошибка при скачивании видео Instagram: {e}")
            if file_path and file_path.exists():
                try:
                    file_path.unlink()
                except Exception as cleanup_err:
                    logger.error(f"Ошибка удаления {file_path}: {cleanup_err}")
            if thumb_path and thumb_path.exists():
                try:
                    thumb_path.unlink()
                except Exception as cleanup_err:
                    logger.error(f"Ошибка удаления {thumb_path}: {cleanup_err}")
            return None

    def cleanup(self, file_info: Dict[str, Any]) -> None:
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