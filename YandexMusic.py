import re
from pathlib import Path
import aiohttp
import aiofiles
from yandex_music import Client
import logging
import asyncio
import os

from tokens import YANDEX_MUSIC_TOKEN

logger = logging.getLogger(__name__)

YANDEX_MUSIC_URL_PATTERN = re.compile(r'https?://music\.yandex\.(?:ru|by|kz|ua)/\S+')
TEMP_DIR = Path("temp_files/YandexMusik")
TEMP_DIR.mkdir(parents=True, exist_ok=True)


def get_url_pattern():
    return YANDEX_MUSIC_URL_PATTERN


def extract_url(text: str) -> str | None:
    match = YANDEX_MUSIC_URL_PATTERN.search(text)
    if match:
        url = match.group()
        logger.info(f"Обнаружена ссылка: {url}")
        return url
    return None


async def download_file(url: str, dest_path: Path) -> bool:
    """Скачивает файл по URL и сохраняет по указанному пути."""
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


async def get_cover_file(cover_uri: str) -> Path | None:
    """Скачивает обложку трека и возвращает путь к временному файлу."""
    if not cover_uri:
        return None
    # Формируем URL для обложки (заменяем %% на размер, например 400x400)
    cover_url = f"https://{cover_uri.replace('%%', '400x400')}"
    # Имя файла: хеш от URL или просто случайное
    cover_filename = f"cover_{abs(hash(cover_url))}.jpg"
    cover_path = TEMP_DIR / cover_filename
    if await download_file(cover_url, cover_path):
        return cover_path
    return None


async def get_music_file(url: str) -> dict | None:
    """
    Скачивает трек по ссылке и возвращает словарь с информацией:
    - file_path: Path до аудиофайла
    - artist: строка с исполнителем
    - title: название трека
    - cover_path: Path до обложки (или None)
    """
    try:
        # Извлекаем ID трека
        track_match = re.search(r'/track/(\d+)', url)
        if not track_match:
            logger.error("Не удалось извлечь ID трека")
            return None
        
        track_id = track_match.group(1)
        
        # Создаем клиент в отдельном потоке
        loop = asyncio.get_event_loop()
        client = await loop.run_in_executor(None, lambda: Client(YANDEX_MUSIC_TOKEN).init())
        
        # Получаем трек
        tracks = await loop.run_in_executor(None, lambda: client.tracks([track_id]))
        if not tracks:
            logger.error(f"Трек {track_id} не найден")
            return None
        
        track = tracks[0]
        
        # Получаем информацию для скачивания
        download_info = await loop.run_in_executor(None, lambda: track.get_download_info())
        if not download_info:
            logger.error("Нет информации для скачивания")
            return None
        
        # Выбираем лучшее качество
        download_info.sort(key=lambda x: x.bitrate_in_kbps, reverse=True)
        best = download_info[0]
        
        # Получаем прямую ссылку
        direct_link = await loop.run_in_executor(None, lambda: best.get_direct_link())
        
        # Формируем имя файла
        artists = ", ".join(artist.name for artist in track.artists)
        title = track.title
        filename = f"{artists} - {title}.mp3"
        # Очищаем имя файла от недопустимых символов
        filename = "".join(c for c in filename if c.isalnum() or c in " ._-").strip()
        file_path = TEMP_DIR / filename
        
        # Скачиваем аудиофайл
        if not await download_file(direct_link, file_path):
            return None
        
        # Скачиваем обложку, если есть
        cover_path = None
        if track.cover_uri:
            cover_path = await get_cover_file(track.cover_uri)
        
        logger.info(f"Файл сохранен: {file_path}")
        return {
            'file_path': file_path,
            'artist': artists,
            'title': title,
            'cover_path': cover_path
        }
        
    except Exception as e:
        logger.exception(f"Ошибка при скачивании трека: {e}")
        return None


def remove_music_file(file_path: Path) -> None:
    """Удаляет временный файл."""
    try:
        if file_path and file_path.exists():
            file_path.unlink()
            logger.info(f"Файл удален: {file_path}")
    except Exception as e:
        logger.error(f"Ошибка при удалении файла {file_path}: {e}")

def remove_cover_file(cover_path: Path) -> None:
    """Удаляет временный файл обложки."""
    if cover_path:
        remove_music_file(cover_path)  # можно использовать ту же функцию