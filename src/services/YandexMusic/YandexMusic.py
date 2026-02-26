import re
import uuid
import logging
import asyncio
import aiohttp
import aiofiles

from pathlib import Path
from yandex_music import Client
from typing import Optional, Dict, Any

from src.services.base import BaseHandler
from src.config import YANDEX_MUSIC_TOKEN, PROJECT_TEMP_DIR

logger = logging.getLogger(__name__)

class YandexMusicHandler(BaseHandler):
    PATTERN = re.compile(r'https?://music\.yandex\.(?:ru|by|kz|ua)/\S+')
    TEMP_DIR = PROJECT_TEMP_DIR / "YandexMusic"
    TEMP_DIR.mkdir(parents=True, exist_ok=True)

    def __init__(self):
        if not YANDEX_MUSIC_TOKEN:
            logger.error("YANDEX_MUSIC_TOKEN не задан. Обработчик Яндекс.Музыки не будет работать.")
        self.token = YANDEX_MUSIC_TOKEN
        self._client = None
        self._lock = asyncio.Lock()  # для потокобезопасности клиента

    async def _get_client(self):
        """Ленивая инициализация клиента с блокировкой."""
        if self._client is None:
            # Инициализация клиента – синхронная операция, выполняем в потоке
            def init_client():
                return Client(self.token).init()
            self._client = await asyncio.to_thread(init_client)
        return self._client

    @property
    def pattern(self) -> re.Pattern:
        return self.PATTERN

    @property
    def source_name(self) -> str:
        return "Яндекс.Музыка"

    async def _download_file(self, url: str, dest_path: Path) -> bool:
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

    async def _get_cover_file(self, cover_uri: str) -> Optional[Path]:
        if not cover_uri:
            return None
        cover_url = f"https://{cover_uri.replace('%%', '400x400')}"
        # Используем uuid для уникальности, но можно оставить хеш для избежания дублей – оставим оба
        cover_hash = uuid.uuid4().hex[:8]
        cover_filename = f"cover_{cover_hash}.jpg"
        cover_path = self.TEMP_DIR / cover_filename
        if await self._download_file(cover_url, cover_path):
            return cover_path
        return None

    async def process(self, url: str, context: str) -> Optional[Dict[str, Any]]:
        if not self.token:
            logger.error("Пропуск обработки: токен Яндекс.Музыки отсутствует")
            return None

        file_path = None
        cover_path = None
        try:
            track_match = re.search(r'/track/(\d+)', url)
            if not track_match:
                logger.error("Не удалось извлечь ID трека")
                return None
            track_id = track_match.group(1)

            # Используем блокировку для безопасного вызова методов клиента
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
                # Добавляем уникальный суффикс
                unique_suffix = uuid.uuid4().hex[:8]
                stem = Path(filename).stem
                ext = Path(filename).suffix
                filename = f"{stem}_{unique_suffix}{ext}"
                file_path = self.TEMP_DIR / filename

            # Скачивание файла (уже вне блокировки, т.к. это aiohttp)
            if not await self._download_file(direct_link, file_path):
                return None

            file_size = file_path.stat().st_size
            if file_size > 50 * 1024 * 1024:
                logger.warning(f"Аудио слишком большое ({file_size} байт). Удаляем.")
                file_path.unlink()
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
        except Exception as e:
            logger.exception(f"Ошибка при скачивании трека: {e}")
            if file_path and file_path.exists():
                try:
                    file_path.unlink()
                except Exception as cleanup_err:
                    logger.error(f"Ошибка удаления {file_path}: {cleanup_err}")
            if cover_path and cover_path.exists():
                try:
                    cover_path.unlink()
                except Exception as cleanup_err:
                    logger.error(f"Ошибка удаления {cover_path}: {cleanup_err}")
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