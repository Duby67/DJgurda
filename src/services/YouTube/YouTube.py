import re
import yt_dlp
import random
import logging
import asyncio

from src.config import YOUTUBE_COOKIES
from src.config import PROJECT_TEMP_DIR

from typing import Optional, Dict, Any
from src.services.base import BaseHandler


logger = logging.getLogger(__name__)

class YouTubeShortsHandler(BaseHandler):
    PATTERN = re.compile(r'https?://(?:www\.)?(?:youtube\.com/shorts/|youtu\.be/)\S+')
    TEMP_DIR = PROJECT_TEMP_DIR / "YouTube"
    TEMP_DIR.mkdir(parents=True, exist_ok=True)

    @property
    def pattern(self) -> re.Pattern:
        return self.PATTERN

    @property
    def source_name(self) -> str:
        return "YouTube"

    async def process(self, url: str, context: str) -> Optional[Dict[str, Any]]:
        try:
            delay = random.uniform(1, 3)
            logger.info(f"Ожидание {delay:.2f} секунд перед скачиванием {url}")
            await asyncio.sleep(delay)
            
            video_id_match = re.search(r'/(?:shorts/|)([a-zA-Z0-9_-]+)', url)
            video_id = video_id_match.group(1) if video_id_match else "unknown"
            file_path = self.TEMP_DIR / f"{video_id}.mp4"
            thumb_path = self.TEMP_DIR / f"{video_id}.jpg"

            ydl_opts = {
                'outtmpl': str(file_path),
                'format': 'best',
                'writethumbnail': True,
                'quiet': True,
                'no_warnings': True,
                #'cookiefile': YOUTUBE_COOKIES,
                'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
                'postprocessors': [{
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': 'mp4',
                }],
                'merge_output_format': 'mp4'
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await asyncio.to_thread(ydl.extract_info, url, download=True)
                if not info:
                    logger.error("Не удалось получить информацию о видео")
                    return None

                if not file_path.exists():
                    logger.error(f"Файл не найден: {file_path}")
                    return None

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
                    'uploader': info.get('uploader', 'Unknown'),
                    'original_url': url,
                    'context': context,
                }
        except Exception as e:
            logger.exception(f"Ошибка при скачивании видео: {e}")
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