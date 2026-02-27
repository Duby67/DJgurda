import re
import uuid
import yt_dlp
import asyncio
import logging
import random
from pathlib import Path
from typing import Optional, Dict, Any
from src.services.base import BaseHandler
from src.config import PROJECT_TEMP_DIR

logger = logging.getLogger(__name__)

class InstagramHandler(BaseHandler):
    PATTERN = re.compile(r'https?://(?:www\.)?instagram\.com/(?:reel|p|tv)/\S+')
    TEMP_DIR = PROJECT_TEMP_DIR / "Instagram"
    TEMP_DIR.mkdir(parents=True, exist_ok=True)

    @property
    def pattern(self) -> re.Pattern:
        return self.PATTERN

    @property
    def source_name(self) -> str:
        return "Instagram"

    async def process(self, url: str, context: str) -> Optional[Dict[str, Any]]:
        file_path = None
        thumb_path = None
        try:
            # Задержка перед скачиванием
            delay = random.uniform(1, 3)
            logger.info(f"Ожидание {delay:.2f} секунд перед скачиванием {url}")
            await asyncio.sleep(delay)

            shortcode_match = re.search(r'/(reel|p|tv)/([a-zA-Z0-9_-]+)', url)
            if not shortcode_match:
                logger.error("Не удалось извлечь код Instagram")
                return None
            shortcode = shortcode_match.group(2)
            unique_id = f"{shortcode}_{uuid.uuid4().hex[:8]}"
            base_path = self.TEMP_DIR / unique_id

            ydl_opts = {
                'outtmpl': str(base_path),  # без расширения
                'format': 'best[ext=mp4]/best',  # предпочитаем готовый mp4
                'writethumbnail': True,
                'quiet': True,
                'no_warnings': True,
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'merge_output_format': 'mp4',   # на случай, если всё же будет раздельная загрузка
                'geo_bypass': True,
                'postprocessors': [{
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': 'mp4',
                }]
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await asyncio.to_thread(ydl.extract_info, url, download=True)
                if not info:
                    logger.error("Не удалось получить информацию о видео Instagram")
                    return None

                # Определяем реальный путь к скачанному файлу
                if 'requested_downloads' in info:
                    downloaded_file = info['requested_downloads'][0]['filepath']
                else:
                    downloaded_file = ydl.prepare_filename(info)
                file_path = Path(downloaded_file)

                if not file_path.exists():
                    logger.error(f"Файл не существует: {file_path}")
                    return None

                # Проверка размера
                file_size = file_path.stat().st_size
                if file_size > 50 * 1024 * 1024:
                    logger.warning(f"Видео слишком большое ({file_size} байт). Удаляем.")
                    file_path.unlink(missing_ok=True)
                    return None

                # Поиск миниатюры (может быть .jpg, .webp, .png)
                possible_thumb = None
                for ext in ['.jpg', '.webp', '.png']:
                    thumb_candidate = file_path.with_suffix(ext)
                    if thumb_candidate.exists():
                        possible_thumb = thumb_candidate
                        break

                return {
                    'type': 'video',
                    'source_name': self.source_name,
                    'file_path': file_path,
                    'thumbnail_path': possible_thumb,
                    'title': info.get('title', 'Unknown'),
                    'uploader': info.get('uploader', info.get('channel', 'Unknown')),
                    'original_url': url,
                    'context': context,
                }

        except Exception as e:
            logger.exception(f"Ошибка при скачивании видео Instagram: {e}")
            # Очистка
            if file_path and file_path.exists():
                file_path.unlink(missing_ok=True)
            if thumb_path and thumb_path.exists():
                thumb_path.unlink(missing_ok=True)
            return None

    def cleanup(self, file_info: Dict[str, Any]) -> None:
        if file_info.get('file_path'):
            try:
                file_info['file_path'].unlink(missing_ok=True)
            except Exception as e:
                logger.error(f"Ошибка удаления {file_info['file_path']}: {e}")
        if file_info.get('thumbnail_path'):
            try:
                file_info['thumbnail_path'].unlink(missing_ok=True)
            except Exception as e:
                logger.error(f"Ошибка удаления {file_info['thumbnail_path']}: {e}")