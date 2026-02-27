import yt_dlp
import aiohttp
import asyncio
import logging
import aiofiles
import requests

from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class VideoMixin:
    async def _download_video(
        self,
        url: str,
        ydl_opts: dict,
        video_id: str = None,
        size_limit: int = None
    ) -> Optional[Dict[str, Any]]:
        if size_limit is None:
            size_limit = getattr(self, 'video_limit', 50 * 1024 * 1024)

        await self._random_delay()

        if video_id is None:
            video_id = self._extract_video_id(url)
        base_path = self._generate_unique_path(video_id)

        default_opts = {
            'outtmpl': str(base_path),
            'quiet': True,
            'no_warnings': True,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'merge_output_format': 'mp4',
            'geo_bypass': True,
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4'
            }]
        }
        default_opts.update(ydl_opts)

        file_path = None
        thumb_path = None

        try:
            with yt_dlp.YoutubeDL(default_opts) as ydl:
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
                    logger.error(f"Файл не существует: {file_path}")
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


class PhotoMixin:
    async def _download_photo(
        self,
        image_url: str,
        dest_path: Path,
        size_limit: int = None
    ) -> bool:
        if size_limit is None:
            size_limit = getattr(self, 'photo_limit', 10 * 1024 * 1024)

        await self._random_delay()

        def sync_download():
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            try:
                response = requests.get(image_url, headers=headers, timeout=10)
                if response.status_code != 200:
                    logger.error(f"Ошибка скачивания {image_url}: {response.status_code}")
                    return False
                with open(dest_path, 'wb') as f:
                    f.write(response.content)
                return True
            except Exception as e:
                logger.exception(f"Ошибка при скачивании изображения: {e}")
                return False

        success = await asyncio.to_thread(sync_download)
        if success:
            file_size = dest_path.stat().st_size
            if file_size > size_limit:
                logger.warning(f"Фото слишком большое ({file_size} байт). Удаляем.")
                dest_path.unlink(missing_ok=True)
                return False
        return success
    
    
class AudioMixin:
    async def _download_file(self, url: str, dest_path: Path) -> bool:
        """Скачивает файл по URL и сохраняет в dest_path, используя aiohttp."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        logger.error(f"Ошибка скачивания {url}: HTTP {response.status}")
                        return False
                    async with aiofiles.open(dest_path, 'wb') as f:
                        await f.write(await response.read())
            return True
        except Exception as e:
            logger.exception(f"Ошибка при скачивании {url}: {e}")
            return False

    async def _download_audio(self, url: str, dest_path: Path, size_limit: int = None) -> bool:
        """Скачивает аудио, проверяет размер, возвращает True при успехе."""
        if size_limit is None:
            size_limit = getattr(self, 'audio_limit', 50 * 1024 * 1024)

        await self._random_delay() 
        success = await self._download_file(url, dest_path)
        if not success:
            return False

        file_size = dest_path.stat().st_size
        if file_size > size_limit:
            logger.warning(f"Аудио слишком большое ({file_size} байт). Удаляем.")
            dest_path.unlink(missing_ok=True)
            return False
        return True

    async def _download_thumbnail(self, url: str, dest_path: Path, size_limit: int = None) -> bool:
        """Скачивает обложку (изображение), проверяет размер."""
        if size_limit is None:
            size_limit = getattr(self, 'photo_limit', 10 * 1024 * 1024)

        await self._random_delay()
        success = await self._download_file(url, dest_path)
        if not success:
            return False

        file_size = dest_path.stat().st_size
        if file_size > size_limit:
            logger.warning(f"Обложка слишком большая ({file_size} байт). Удаляем.")
            dest_path.unlink(missing_ok=True)
            return False
        return True
    
    
