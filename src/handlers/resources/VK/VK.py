import re
import yt_dlp
import logging
import asyncio

from pathlib import Path
from typing import Optional, Dict, Any

from src.handlers.base import BaseHandler
from src.handlers.mixins import VideoMixin

logger = logging.getLogger(__name__)

class VKHandler(BaseHandler, VideoMixin):
    PATTERN = re.compile(
        r'https?://(?:www\.|m\.)?(?:vk\.com|vk\.ru|vk\.cc)/(?:video|audio|wall|clip)[\w\-]+'
    )

    @property
    def pattern(self) -> re.Pattern:
        return self.PATTERN

    @property
    def source_name(self) -> str:
        return "VK"

    async def _download_audio_ytdlp(
        self,
        url: str,
        video_id: Optional[str] = None,
        size_limit: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        
        if size_limit is None:
            size_limit = getattr(self, 'audio_limit', 50 * 1024 * 1024)

        await self._random_delay()

        if video_id is None:
            video_id = self._extract_video_id(url)
        base_path = self._generate_unique_path(video_id)

        ydl_opts = {
            'outtmpl': str(base_path),
            'quiet': True,
            'no_warnings': True,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'geo_bypass': True,
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'writethumbnail': True,
            'embedthumbnail': True,
        }

        file_path = None
        thumb_path = None

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await asyncio.to_thread(ydl.extract_info, url, download=True)
                if not info:
                    logger.error("Failed to get audio information")
                    return None

                # Определяем путь к скачанному файлу
                if 'requested_downloads' in info:
                    downloaded_file = info['requested_downloads'][0]['filepath']
                else:
                    # yt-dlp после конвертации может изменить расширение
                    downloaded_file = str(base_path) + '.mp3'
                file_path = Path(downloaded_file)

                if not file_path.exists():
                    # Попробуем найти файл с расширением .mp3 в temp_dir
                    possible = list(self.temp_dir.glob(f"{base_path.stem}*.mp3"))
                    if possible:
                        file_path = possible[0]
                    else:
                        logger.error(f"File not found: {file_path}")
                        return None

                file_size = file_path.stat().st_size
                if file_size > size_limit:
                    logger.warning(f"Audio file is too large ({file_size} bytes). Removing.")
                    file_path.unlink(missing_ok=True)
                    return None

                # Поиск обложки (thumbnail)
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
            logger.exception("Failed to download VK audio: %s", exc)
            if file_path and file_path.exists():
                file_path.unlink(missing_ok=True)
            if thumb_path and thumb_path.exists():
                thumb_path.unlink(missing_ok=True)
            return None

    async def process(self, url: str, context: str, resolved_url: Optional[str] = None) -> Optional[Dict[str, Any]]:
        target_url = resolved_url or url
        video_id = self._extract_video_id(target_url)

        # Определяем тип контента по наличию подстроки /video или /audio
        if '/video' in target_url:
            # Видео
            ydl_opts = {
                'format': 'best[ext=mp4]/best',
                'writethumbnail': True,
            }
            result = await self._download_video(target_url, ydl_opts, video_id=video_id)
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
        elif '/audio' in target_url:
            # Аудио
            result = await self._download_audio_ytdlp(target_url, video_id=video_id)
            if not result:
                return None
            info = result['info']
            return {
                'type': 'audio',
                'source_name': self.source_name,
                'file_path': result['file_path'],
                'thumbnail_path': result['thumbnail_path'],
                'title': info.get('title', 'Unknown'),
                'uploader': info.get('uploader', info.get('channel', 'Unknown')),
                'original_url': url,
                'context': context,
            }
        else:
            # Возможно, ссылка на стену или клип — пробуем как видео (клипы тоже видео)
            # Также можно обработать /wall? но пока просто пробуем видео
            ydl_opts = {
                'format': 'best[ext=mp4]/best',
                'writethumbnail': True,
            }
            result = await self._download_video(target_url, ydl_opts, video_id=video_id)
            if result:
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
            return None
