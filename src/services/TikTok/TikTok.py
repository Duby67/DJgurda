import re
import asyncio
import logging
import requests

from bs4 import BeautifulSoup
from typing import Optional, Dict, Any

from src.services.base import BaseHandler
from src.services.mixins import VideoMixin, PhotoMixin

logger = logging.getLogger(__name__)

class TikTokHandler(BaseHandler, VideoMixin, PhotoMixin):
    PATTERN = re.compile(r'https?://(?:www\.|vm\.|vt\.)?tiktok\.com/\S+')

    @property
    def pattern(self) -> re.Pattern:
        return self.PATTERN

    @property
    def source_name(self) -> str:
        return "TikTok"

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
        if '/photo/' in url:
            await self._random_delay()
            video_id_match = re.search(r'/(\d+)[?/]?', url)
            video_id = video_id_match.group(1) if video_id_match else "unknown"
            dest_path = self._generate_unique_path(video_id, suffix=".jpg")
            photo_info = await self._extract_photo_info(url)
            if not photo_info:
                return None

            if not await self._download_photo(photo_info['img_url'], dest_path):
                return None

            return {
                'type': 'photo',
                'source_name': self.source_name,
                'file_path': dest_path,
                'thumbnail_path': None,
                'title': photo_info['title'],
                'uploader': photo_info['uploader'],
                'original_url': url,
                'context': context,
            }
        else:
            video_id_match = re.search(r'/(\d+)[?/]?', url)
            video_id = video_id_match.group(1) if video_id_match else self._extract_video_id(url)
            ydl_opts = {
                'format': 'best[ext=mp4]/best',
                'writethumbnail': True,
            }
            result = await self._download_video(url, ydl_opts, video_id=video_id)
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