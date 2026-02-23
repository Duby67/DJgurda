import re
import asyncio
import logging
from pathlib import Path
import yt_dlp

logger = logging.getLogger(__name__)

# Регулярное выражение для ссылок на YouTube Shorts
YOUTUBE_SHORTS_URL_PATTERN = re.compile(
    r'https?://(?:www\.)?(?:youtube\.com/shorts/|youtu\.be/)[a-zA-Z0-9_-]+'
)

TEMP_DIR = Path("temp_files/YouTubeShorts")
TEMP_DIR.mkdir(parents=True, exist_ok=True)


def get_url_pattern():
    """Возвращает скомпилированное регулярное выражение для фильтрации сообщений."""
    return YOUTUBE_SHORTS_URL_PATTERN


def extract_urls(text: str) -> str | None:
    """Извлекает ссылки на YouTube Shorts из текста."""
    urls = YOUTUBE_SHORTS_URL_PATTERN.findall(text)
    if urls:
        logger.info(f"Обнаружены ссылки на YouTube Shorts: {urls}")
        return urls
    logger.info("Ссылки на YouTube Shorts не найдены")
    return None

def parse_urls_with_context(text: str) -> list[tuple[str, str]]:
    """
    Разбивает текст по ссылкам на YouTube Shorts.
    Возвращает список кортежей (url, контекст_пользователя).
    """
    urls = extract_urls(text)
    if not urls:
        return []

    parts = YOUTUBE_SHORTS_URL_PATTERN.split(text)
    result = []
    for i, url in enumerate(urls):
        before = parts[i].strip()
        if i == len(urls) - 1:
            after = parts[i + 1].strip()
            user_text = (before + " " + after).strip()
        else:
            user_text = before
        result.append((url, user_text))
    return result

async def download_video(url: str) -> dict | None:
    """
    Скачивает видео и возвращает словарь с информацией:
    - file_path: Path до видеофайла
    - title: название видео
    - uploader: автор видео
    - thumbnail_path: Path до миниатюры (или None)
    """
    try:
        # Извлекаем ID видео для имени файла
        video_id_match = re.search(r'/(?:shorts/|)([a-zA-Z0-9_-]+)', url)
        video_id = video_id_match.group(1) if video_id_match else "unknown"
        file_path = TEMP_DIR / f"{video_id}.mp4"
        thumb_path = TEMP_DIR / f"{video_id}.jpg"

        # Настройки yt-dlp
        ydl_opts = {
            'outtmpl': str(file_path),          # шаблон имени файла
            'format': 'best[ext=mp4]',          # лучшее качество в MP4
            'writethumbnail': True,              # скачать обложку
            'quiet': True,
            'no_warnings': True,
        }

        loop = asyncio.get_event_loop()
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Скачиваем видео и получаем информацию (блокирующая операция – в executor)
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=True))
            if not info:
                logger.error("Не удалось получить информацию о видео")
                return None

            # Проверяем, что файл существует
            if not file_path.exists():
                logger.error(f"Файл не найден: {file_path}")
                return None

            # Проверяем размер (Telegram‑боты ограничены 50 МБ)
            file_size = file_path.stat().st_size
            if file_size > 50 * 1024 * 1024:
                logger.warning(f"Видео слишком большое ({file_size} байт). Удаляем.")
                file_path.unlink()
                return None

            # Ищем миниатюру (yt-dlp сохраняет рядом с видео, обычно .jpg)
            possible_thumb = file_path.with_suffix('.jpg')
            if possible_thumb.exists():
                thumb_path = possible_thumb
            else:
                thumb_path = None

            return {
                'file_path': file_path,
                'title': info.get('title', 'Unknown'),
                'uploader': info.get('uploader', 'Unknown'),
                'thumbnail_path': thumb_path,
            }

    except Exception as e:
        logger.exception(f"Ошибка при скачивании видео: {e}")
        return None


def remove_video_file(file_path: Path) -> None:
    """Удаляет временный видеофайл."""
    try:
        if file_path and file_path.exists():
            file_path.unlink()
            logger.info(f"Видеофайл удалён: {file_path}")
    except Exception as e:
        logger.error(f"Ошибка удаления видеофайла {file_path}: {e}")


def remove_thumbnail_file(thumb_path: Path) -> None:
    """Удаляет временный файл миниатюры."""
    if thumb_path:
        remove_video_file(thumb_path)  # та же функция подходит
        
