import re
import uuid
import yt_dlp
import asyncio
import logging
import requests
import random
from pathlib import Path
from bs4 import BeautifulSoup
from typing import Optional, Dict, Any
from src.services.base import BaseHandler
from src.config import PROJECT_TEMP_DIR

logger = logging.getLogger(__name__)

class TikTokHandler(BaseHandler):
    PATTERN = re.compile(r'https?://(?:www\.|vm\.|vt\.)?tiktok\.com/\S+')
    TEMP_DIR = PROJECT_TEMP_DIR / "TikTok"
    TEMP_DIR.mkdir(parents=True, exist_ok=True)

    @property
    def pattern(self) -> re.Pattern:
        return self.PATTERN

    @property
    def source_name(self) -> str:
        return "TikTok"

    async def _download_image(self, url: str, dest_path: Path) -> bool:
        def sync_download():
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            try:
                response = requests.get(url, headers=headers, timeout=10)
                if response.status_code != 200:
                    logger.error(f"Ошибка скачивания {url}: {response.status_code}")
                    return False
                with open(dest_path, 'wb') as f:
                    f.write(response.content)
                return True
            except Exception as e:
                logger.exception(f"Ошибка при скачивании изображения: {e}")
                return False
        return await asyncio.to_thread(sync_download)

    async def _extract_photo_info(self, url: str) -> Optional[Dict]:
        def sync_extract():
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            try:
                resp = requests.get(url, headers=headers, timeout=10)
                if resp.status_code != 200:
                    logger.error(f"HTTP {resp.status_code} при загрузке страницы фото")
                    return None
                soup = BeautifulSoup(resp.text, 'html.parser')
                og_image = soup.find('meta', property='og:image')
                img_url = og_image.get('content') if og_image else None
                if not img_url:
                    img_tag = soup.find('img', {'class': 'tiktok-media'}) or soup.find('img', {'src': re.compile(r'^https://.*\.(jpg|jpeg|png)')})
                    if img_tag and img_tag.get('src'):
                        img_url = img_tag['src']
                    else:
                        logger.error("Не удалось найти ссылку на изображение")
                        return None
                title_tag = soup.find('meta', property='og:title')
                title = title_tag['content'] if title_tag else "TikTok Photo"
                uploader = "Unknown"
                if ' — ' in title:
                    uploader = title.split(' — ')[0].strip()
                elif ' on TikTok' in title:
                    uploader = title.split(' on TikTok')[0].strip()
                return {
                    'img_url': img_url,
                    'title': title,
                    'uploader': uploader
                }
            except Exception as e:
                logger.exception(f"Ошибка парсинга фото TikTok: {e}")
                return None
        return await asyncio.to_thread(sync_extract)

    async def process(self, url: str, context: str) -> Optional[Dict[str, Any]]:
        file_path = None
        thumb_path = None
        try:
            # Задержка перед скачиванием
            delay = random.uniform(1, 3)
            logger.info(f"Ожидание {delay:.2f} секунд перед скачиванием {url}")
            await asyncio.sleep(delay)

            video_id_match = re.search(r'/(\d+)[?/]?', url)
            video_id = video_id_match.group(1) if video_id_match else "unknown"
            unique_id = f"{video_id}_{uuid.uuid4().hex[:8]}"

            if '/photo/' in url:
                # Обработка фото
                file_path = self.TEMP_DIR / f"{unique_id}.jpg"
                photo_info = await self._extract_photo_info(url)
                if not photo_info:
                    return None
                if not await self._download_image(photo_info['img_url'], file_path):
                    return None
                file_size = file_path.stat().st_size
                if file_size > 10 * 1024 * 1024:
                    logger.warning(f"Фото слишком большое ({file_size} байт). Удаляем.")
                    file_path.unlink(missing_ok=True)
                    return None
                return {
                    'type': 'photo',
                    'source_name': self.source_name,
                    'file_path': file_path,
                    'thumbnail_path': None,
                    'title': photo_info['title'],
                    'uploader': photo_info['uploader'],
                    'original_url': url,
                    'context': context,
                }
            else:
                # Обработка видео
                base_path = self.TEMP_DIR / unique_id
                ydl_opts = {
                    'outtmpl': str(base_path),
                    'format': 'best[ext=mp4]/best',  # предпочитаем готовый mp4
                    'writethumbnail': True,
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

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = await asyncio.to_thread(ydl.extract_info, url, download=True)
                    if not info:
                        logger.error("Не удалось получить информацию о видео TikTok")
                        return None

                    # Определяем реальный путь
                    if 'requested_downloads' in info:
                        downloaded_file = info['requested_downloads'][0]['filepath']
                    else:
                        downloaded_file = ydl.prepare_filename(info)
                    file_path = Path(downloaded_file)

                    if not file_path.exists():
                        logger.error(f"Файл не существует: {file_path}")
                        return None

                    file_size = file_path.stat().st_size
                    if file_size > 50 * 1024 * 1024:
                        logger.warning(f"Видео слишком большое ({file_size} байт). Удаляем.")
                        file_path.unlink(missing_ok=True)
                        return None

                    # Поиск миниатюры
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
            logger.exception(f"Ошибка при скачивании TikTok: {e}")
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