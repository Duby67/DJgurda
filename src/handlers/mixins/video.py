import yt_dlp
import asyncio
import logging

from pathlib import Path
from typing import Optional, Dict, Any

from .base import BaseMixin

logger = logging.getLogger(__name__)

class VideoMixin(BaseMixin):
    async def _download_video(
        self,
        url: str,
        ydl_opts: dict,
        video_id: str = None,
        size_limit: int = None
    ) -> Optional[Dict[str, Any]]:
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

                if 'requested_downloads' in info:
                    downloaded_file = info['requested_downloads'][0]['filepath']
                else:
                    downloaded_file = ydl.prepare_filename(info)
                file_path = Path(downloaded_file)

                if not file_path.exists():
                    candidates = list(self.temp_dir.glob(f"{base_path.stem}*"))
                    if candidates:
                        file_path = candidates[0]
                    else:
                        logger.error(f"Файл не найден: {file_path}")
                        return None

                file_size = file_path.stat().st_size
                if file_size > size_limit:
                    logger.warning(f"Видео слишком большое ({file_size} байт). Удаляем.")
                    file_path.unlink(missing_ok=True)
                    return None

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

        except Exception as e:
            logger.exception(f"Ошибка при скачивании видео: {e}")
            if file_path and file_path.exists():
                file_path.unlink(missing_ok=True)
            if thumb_path and thumb_path.exists():
                thumb_path.unlink(missing_ok=True)
            return None