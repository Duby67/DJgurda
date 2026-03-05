import re
import asyncio
import aiohttp
import logging

from bs4 import BeautifulSoup
from typing import Optional, Dict, Any

from src.handlers.mixins import PhotoMixin

logger = logging.getLogger(__name__)

class TikTokPhoto(PhotoMixin):
    async def _extract_photo_info(self, url: str) -> Optional[Dict]:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=10) as resp:
                    if resp.status != 200:
                        logger.error(f"HTTP {resp.status} при загрузке страницы фото")
                        return None
                    html = await resp.text()
                    soup = await asyncio.to_thread(BeautifulSoup, html, 'html.parser')
                
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

    async def _process_tiktok_photo(
        self,
        url: str,
        context: str,
        resolved_url: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        
        target_url = resolved_url or url
        photo_id_match = re.search(r'/(\d+)[?/]?', target_url)
        photo_id = photo_id_match.group(1) if photo_id_match else "unknown"
        dest_path = self._generate_unique_path(photo_id, suffix=".jpg")

        await self._random_delay()
        
        photo_info = await self._extract_photo_info(target_url)
        if not photo_info:
            return None

        if not await self._download_photo(photo_info['img_url'], dest_path):
            return None

        return {
            'type': 'photo',
            'source_name': 'TikTok',
            'file_path': dest_path,
            'thumbnail_path': None,
            'title': photo_info['title'],
            'uploader': photo_info['uploader'],
            'original_url': url,
            'context': context,
        }