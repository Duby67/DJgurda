"""
Миксин для обработки видео.

Использует yt-dlp для загрузки видео с поддержкой миниатюр и метаданных.
"""

import yt_dlp
import asyncio
import logging

from pathlib import Path
from typing import Any, Dict, Optional

from .base import BaseMixin

logger = logging.getLogger(__name__)


class VideoMixin(BaseMixin):
    """
    Миксин для загрузки и обработки видео через yt-dlp.
    """
    
    async def _download_video(
        self,
        url: str,
        ydl_opts: Dict[str, Any],
        video_id: Optional[str] = None,
        size_limit: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Скачивает видео через yt-dlp.
        
        Аргументы:
            url: URL видео
            ydl_opts: Опции для yt-dlp
            video_id: Идентификатор видео (опционально)
            size_limit: Лимит размера файла в байтах
            
        Возвращает:
            Словарь с путями к файлу и миниатюре, либо None при ошибке
        """
        if size_limit is None:
            size_limit = self.video_limit

        await self._random_delay()

        if video_id is None:
            video_id = self._extract_video_id(url)
        base_path = self._generate_unique_path(video_id)

        default_opts = {
            'outtmpl': str(base_path),
            'quiet': True,
            'no_warnings': True,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'geo_bypass': True,
        }
        merged_opts = {**default_opts, **ydl_opts}

        file_path = None
        thumb_path = None

        try:
            with yt_dlp.YoutubeDL(merged_opts) as ydl:
                info = await asyncio.to_thread(ydl.extract_info, url, download=True)
                if not info:
                    logger.error("Не удалось получить информацию о видео")
                    return None

                # Определяем путь к скачанному файлу
                if 'requested_downloads' in info:
                    downloaded_file = info['requested_downloads'][0]['filepath']
                else:
                    downloaded_file = ydl.prepare_filename(info)
                file_path = Path(downloaded_file)

                # Ищем файл если он был переименован
                if not file_path.exists():
                    candidates = list(self.temp_dir.glob(f"{base_path.stem}*"))
                    if candidates:
                        file_path = candidates[0]
                    else:
                        logger.error(f"Файл не найден: {file_path}")
                        return None

                # Проверяем размер файла
                file_size = file_path.stat().st_size
                if file_size > size_limit:
                    logger.warning(f"Видео слишком большое ({file_size} байт). Удаляем.")
                    file_path.unlink(missing_ok=True)
                    return None

                # Ищем миниатюру
                for ext in ['.jpg', '.webp', '.png']:
                    thumb_candidate = file_path.with_suffix(ext)
                    if thumb_candidate.exists():
                        thumb_path = thumb_candidate
                        break

                return {
                    'file_path': file_path,
                    'thumbnail_path': thumb_path,
                    'info': info
                }

        except Exception as exc:
            logger.exception("Ошибка при скачивании видео: %s", exc)
            # Очищаем временные файлы при ошибке
            if file_path and file_path.exists():
                file_path.unlink(missing_ok=True)
            if thumb_path and thumb_path.exists():
                thumb_path.unlink(missing_ok=True)
            return None
