import re
from pathlib import Path
import aiohttp
import aiofiles
from yandex_music import Client
import logging
import asyncio

logger = logging.getLogger(__name__)

class YandexMusicHandler:
    PATTERN = re.compile(r'https?://music\.yandex\.(?:ru|by|kz|ua)/\S+')
    TEMP_DIR = Path("temp_files/YandexMusik")
    TEMP_DIR.mkdir(parents=True, exist_ok=True)

    def __init__(self):
        from tokens import YANDEX_MUSIC_TOKEN
        self.token = YANDEX_MUSIC_TOKEN

    @property
    def pattern(self):
        return self.PATTERN

    async def _download_file(self, url: str, dest_path: Path) -> bool:
        """Скачивает файл по URL."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        logger.error(f"Ошибка скачивания файла {url}: HTTP {response.status}")
                        return False
                    async with aiofiles.open(dest_path, 'wb') as f:
                        await f.write(await response.read())
            return True
        except Exception as e:
            logger.exception(f"Ошибка при скачивании {url}: {e}")
            return False

    async def _get_cover_file(self, cover_uri: str) -> Path | None:
        """Скачивает обложку трека."""
        if not cover_uri:
            return None
        cover_url = f"https://{cover_uri.replace('%%', '400x400')}"
        cover_filename = f"cover_{abs(hash(cover_url))}.jpg"
        cover_path = self.TEMP_DIR / cover_filename
        if await self._download_file(cover_url, cover_path):
            return cover_path
        return None

    async def process(self, url: str, context: str) -> dict | None:
        try:
            # Извлекаем ID трека
            track_match = re.search(r'/track/(\d+)', url)
            if not track_match:
                logger.error("Не удалось извлечь ID трека")
                return None

            track_id = track_match.group(1)

            loop = asyncio.get_event_loop()
            # Инициализация клиента в отдельном потоке
            client = await loop.run_in_executor(None, lambda: Client(self.token).init())

            # Получаем трек
            tracks = await loop.run_in_executor(None, lambda: client.tracks([track_id]))
            if not tracks:
                logger.error(f"Трек {track_id} не найден")
                return None

            track = tracks[0]

            # Информация для скачивания
            download_info = await loop.run_in_executor(None, lambda: track.get_download_info())
            if not download_info:
                logger.error("Нет информации для скачивания")
                return None

            # Выбираем лучшее качество
            download_info.sort(key=lambda x: x.bitrate_in_kbps, reverse=True)
            best = download_info[0]

            direct_link = await loop.run_in_executor(None, lambda: best.get_direct_link())

            # Формируем имя файла
            artists = ", ".join(artist.name for artist in track.artists)
            title = track.title
            filename = f"{artists} - {title}.mp3"
            filename = "".join(c for c in filename if c.isalnum() or c in " ._-").strip()
            file_path = self.TEMP_DIR / filename

            # Скачиваем аудио
            if not await self._download_file(direct_link, file_path):
                return None

            # Скачиваем обложку
            cover_path = None
            if track.cover_uri:
                cover_path = await self._get_cover_file(track.cover_uri)

            logger.info(f"Файл сохранен: {file_path}")
            return {
                'type': 'audio',
                'file_path': file_path,
                'thumbnail_path': cover_path,
                'title': title,
                'performer': artists,
                'original_url': url,
                'context': context,
            }
        except Exception as e:
            logger.exception(f"Ошибка при скачивании трека: {e}")
            return None

    def cleanup(self, file_info: dict):
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