import re
import uuid
import logging
import asyncio

from pathlib import Path
from yandex_music import Client
from typing import Optional, Dict, Any

from src.config import YANDEX_MUSIC_TOKEN
from src.handlers.base import BaseHandler
from src.handlers.mixins import AudioMixin

logger = logging.getLogger(__name__)

class YandexMusicHandler(BaseHandler, AudioMixin):
    PATTERN = re.compile(
    r'https?://(?:music\.yandex\.(?:ru|by|kz|ua)/|yandex\.ru/music/)\S+'
    )

    def __init__(self) -> None:
        super().__init__()
        if not YANDEX_MUSIC_TOKEN:
            logger.error("YANDEX_MUSIC_TOKEN не задан. Обработчик Яндекс.Музыки не будет работать.")
        self.token = YANDEX_MUSIC_TOKEN
        self._client = None
        self._lock = asyncio.Lock()

    async def _get_client(self) -> Client:
        if self._client is None:
            def init_client():
                return Client(self.token).init()
            self._client = await asyncio.to_thread(init_client)
        return self._client

    @property
    def pattern(self) -> re.Pattern:
        return self.PATTERN

    @property
    def source_name(self) -> str:
        return "Yandex.Music"

    async def _get_cover_file(self, cover_uri: str) -> Optional[Path]:
        if not cover_uri:
            return None
        cover_url = f"https://{cover_uri.replace('%%', '400x400')}"
        cover_filename = f"cover_{uuid.uuid4().hex[:8]}.jpg"
        cover_path = self.temp_dir / cover_filename
        if await self._download_thumbnail(cover_url, cover_path, self.photo_limit):
            return cover_path
        return None

    async def process(self, url: str, context: str, resolved_url: Optional[str] = None) -> Optional[Dict[str, Any]]:
        target_url = resolved_url or url
        if not self.token:
            logger.error("Пропуск обработки: токен Яндекс.Музыки отсутствует")
            return None

        file_path = None
        cover_path = None
        try:
            track_match = re.search(r'/track/(\d+)', target_url)
            if not track_match:
                logger.error("Не удалось извлечь ID трека")
                return None
            track_id = track_match.group(1)

            async with self._lock:
                client = await self._get_client()
                tracks = await asyncio.to_thread(client.tracks, [track_id])
                if not tracks:
                    logger.error(f"Трек {track_id} не найден")
                    return None
                track = tracks[0]

                download_info = await asyncio.to_thread(track.get_download_info)
                if not download_info:
                    logger.error("Нет информации для скачивания")
                    return None

                download_info.sort(key=lambda x: x.bitrate_in_kbps, reverse=True)
                best = download_info[0]
                direct_link = await asyncio.to_thread(best.get_direct_link)

                artists = ", ".join(artist.name for artist in track.artists)
                title = track.title
                filename = f"{artists} - {title}.mp3"
                filename = "".join(c for c in filename if c.isalnum() or c in " ._-").strip()
                unique_suffix = uuid.uuid4().hex[:8]
                stem = Path(filename).stem
                ext = Path(filename).suffix
                filename = f"{stem}_{unique_suffix}{ext}"
                file_path = self.temp_dir / filename

            if not await self._download_audio(direct_link, file_path, self.audio_limit):
                return None

            if track.cover_uri:
                cover_path = await self._get_cover_file(track.cover_uri)

            logger.info(f"Файл сохранен: {file_path}")
            return {
                'type': 'audio',
                'source_name': self.source_name,
                'file_path': file_path,
                'thumbnail_path': cover_path,
                'title': title,
                'uploader': artists,
                'original_url': url,
                'context': context,
            }
        except Exception as exc:
            logger.exception("Ошибка при скачивании трека: %s", exc)
            if file_path and file_path.exists():
                file_path.unlink(missing_ok=True)
            if cover_path and cover_path.exists():
                cover_path.unlink(missing_ok=True)
            return None
