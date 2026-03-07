"""
Обработчик фото и слайдшоу TikTok.
"""

import re
from pathlib import Path
import logging
from urllib.parse import urlsplit
from typing import Optional, Dict, Any

import aiohttp

from src.handlers.mixins import PhotoMixin, AudioMixin, MediaGroupMixin

logger = logging.getLogger(__name__)

class TikTokPhoto(PhotoMixin, AudioMixin, MediaGroupMixin):
    """
    Миксин для обработки фото и слайдшоу TikTok.
    """
    TIKWM_API_URL = "https://www.tikwm.com/api/"
    TIKWM_TIMEOUT = 20
    DEFAULT_BACKGROUND_TRACK_TITLE = "Фоновая музыка TikTok"
    DEFAULT_BACKGROUND_TRACK_PERFORMER = "TikTok"

    @staticmethod
    def _suffix_from_url(media_url: str, default_suffix: str) -> str:
        """
        Возвращает расширение файла из URL или дефолтное значение.
        """
        suffix = Path(urlsplit(media_url).path).suffix.lower()
        if not suffix or len(suffix) > 5:
            return default_suffix
        return suffix

    def _extract_music_metadata_from_tikwm(self, media_data: Dict[str, Any]) -> Dict[str, str]:
        """
        Извлекает название трека и исполнителя из payload TikWM.
        """
        music_info = media_data.get('music_info') if isinstance(media_data, dict) else None
        music_info = music_info if isinstance(music_info, dict) else {}

        track_title = music_info.get('title')
        track_author = music_info.get('author')

        if not isinstance(track_title, str) or not track_title.strip():
            track_title = self.DEFAULT_BACKGROUND_TRACK_TITLE
        if not isinstance(track_author, str) or not track_author.strip():
            track_author = self.DEFAULT_BACKGROUND_TRACK_PERFORMER

        return {
            'title': track_title.strip(),
            'performer': track_author.strip(),
        }

    @staticmethod
    def _extract_first_http_url(value: Any) -> Optional[str]:
        """
        Пытается извлечь первый HTTP(S)-URL из произвольной структуры.
        """
        if isinstance(value, str):
            return value if value.startswith(('http://', 'https://')) else None

        if isinstance(value, (list, tuple)):
            for item in value:
                found = TikTokPhoto._extract_first_http_url(item)
                if found:
                    return found
            return None

        if isinstance(value, dict):
            preferred_keys = (
                'url', 'src', 'cover', 'cover_url', 'cover_hd',
                'origin_cover', 'thumbnail', 'thumb'
            )
            for key in preferred_keys:
                if key in value:
                    found = TikTokPhoto._extract_first_http_url(value.get(key))
                    if found:
                        return found
            for nested_value in value.values():
                found = TikTokPhoto._extract_first_http_url(nested_value)
                if found:
                    return found
            return None

        return None

    def _extract_music_cover_url_from_tikwm(self, media_data: Dict[str, Any]) -> Optional[str]:
        """
        Извлекает URL обложки трека из payload TikWM.
        """
        if not isinstance(media_data, dict):
            return None

        candidates = [
            media_data.get('music_info'),
            media_data.get('music_cover'),
            media_data.get('cover'),
            media_data.get('origin_cover'),
            media_data.get('ai_dynamic_cover'),
        ]
        for candidate in candidates:
            found = self._extract_first_http_url(candidate)
            if found:
                return found
        return None

    def _extract_music_metadata_from_info(self, info: Dict[str, Any]) -> Dict[str, str]:
        """
        Извлекает название трека и исполнителя из данных yt-dlp.
        """
        if not isinstance(info, dict):
            return {
                'title': self.DEFAULT_BACKGROUND_TRACK_TITLE,
                'performer': self.DEFAULT_BACKGROUND_TRACK_PERFORMER,
            }

        track_title = info.get('track')
        track_author = None

        artists = info.get('artists')
        if isinstance(artists, list):
            for artist in artists:
                if isinstance(artist, str) and artist.strip():
                    track_author = artist.strip()
                    break

        if not track_author:
            artist = info.get('artist')
            if isinstance(artist, str) and artist.strip():
                track_author = artist.strip()

        if not isinstance(track_title, str) or not track_title.strip():
            track_title = self.DEFAULT_BACKGROUND_TRACK_TITLE
        if not isinstance(track_author, str) or not track_author.strip():
            track_author = self.DEFAULT_BACKGROUND_TRACK_PERFORMER

        return {
            'title': track_title.strip(),
            'performer': track_author.strip(),
        }

    def _extract_music_cover_url_from_info(self, info: Dict[str, Any]) -> Optional[str]:
        """
        Извлекает URL обложки трека из данных yt-dlp.
        """
        if not isinstance(info, dict):
            return None

        candidates = [
            info.get('thumbnail'),
            info.get('thumbnails'),
            info.get('cover'),
            info.get('album_art'),
            info.get('artwork_url'),
        ]
        for candidate in candidates:
            found = self._extract_first_http_url(candidate)
            if found:
                return found
        return None

    async def _fetch_tikwm_payload(self, target_url: str) -> Optional[Dict[str, Any]]:
        """
        Получает данные о photo/slideshow посте через внешний API TikWM.
        """
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://www.tikwm.com/',
        }
        payload = {'url': target_url, 'hd': '1'}

        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.post(
                    self.TIKWM_API_URL,
                    data=payload,
                    timeout=self.TIKWM_TIMEOUT,
                ) as resp:
                    if resp.status != 200:
                        logger.warning("TikWM API HTTP %s for %s", resp.status, target_url)
                        return None
                    data = await resp.json(content_type=None)
        except Exception as exc:
            logger.warning("TikWM API request failed for %s: %s", target_url, exc)
            return None

        if not isinstance(data, dict):
            logger.warning("TikWM API returned invalid payload type for %s", target_url)
            return None

        if data.get('code') != 0:
            logger.warning("TikWM API returned code=%s for %s", data.get('code'), target_url)
            return None

        media_data = data.get('data')
        if not isinstance(media_data, dict):
            logger.warning("TikWM API returned invalid data field for %s", target_url)
            return None

        return media_data

    async def _build_from_tikwm_payload(
        self,
        *,
        target_url: str,
        original_url: str,
        context: str,
        photo_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Формирует результат обработчика на основе данных TikWM.
        """
        media_data = await self._fetch_tikwm_payload(target_url)
        if not media_data:
            return None

        image_urls = [
            image_url
            for image_url in media_data.get('images', [])
            if isinstance(image_url, str) and image_url.startswith('http')
        ]
        if not image_urls:
            logger.warning("TikWM returned no images for %s", target_url)
            return None

        photos = []
        for index, image_url in enumerate(image_urls, start=1):
            photo_path = self._generate_unique_path(
                f"{photo_id}_photo_{index}",
                suffix=self._suffix_from_url(image_url, ".jpg"),
            )
            if await self._download_photo(image_url, photo_path, size_limit=self.photo_limit):
                photos.append({'file_path': photo_path, 'type': 'photo', 'info': media_data})

        if not photos:
            logger.error("Failed to download photos from TikWM payload for %s", target_url)
            return None

        title = media_data.get('title') or "TikTok Photo"
        author_info = media_data.get('author') if isinstance(media_data.get('author'), dict) else {}
        uploader = (
            author_info.get('nickname')
            or author_info.get('unique_id')
            or author_info.get('id')
            or "Unknown"
        )

        music_url = media_data.get('music')
        has_music = isinstance(music_url, str) and music_url.startswith('http')

        if len(photos) == 1 and not has_music:
            return {
                'type': 'photo',
                'source_name': 'TikTok',
                'file_path': photos[0]['file_path'],
                'thumbnail_path': None,
                'title': title,
                'uploader': uploader,
                'original_url': original_url,
                'context': context,
            }

        result: Dict[str, Any] = {
            'type': 'media_group',
            'source_name': 'TikTok',
            'files': [{'file_path': p['file_path'], 'type': 'photo'} for p in photos],
            'original_url': original_url,
            'context': context,
            'title': title,
            'uploader': uploader,
        }

        if has_music:
            music_meta = self._extract_music_metadata_from_tikwm(media_data)
            audio_path = self._generate_unique_path(
                f"{photo_id}_audio",
                suffix=self._suffix_from_url(music_url, ".m4a"),
            )
            if await self._download_audio(music_url, audio_path, size_limit=self.audio_limit):
                audio_info: Dict[str, Any] = {
                    'file_path': audio_path,
                    'title': music_meta['title'],
                    'performer': music_meta['performer'],
                }
                music_cover_url = self._extract_music_cover_url_from_tikwm(media_data)
                if music_cover_url:
                    cover_path = self._generate_unique_path(
                        f"{photo_id}_audio_cover",
                        suffix=self._suffix_from_url(music_cover_url, ".jpg"),
                    )
                    if await self._download_thumbnail(music_cover_url, cover_path, size_limit=self.photo_limit):
                        audio_info['thumbnail_path'] = cover_path
                    else:
                        logger.warning("Failed to download TikTok music cover for %s", target_url)

                result['audio'] = audio_info
            else:
                logger.warning("Failed to download TikTok music for %s", target_url)

        return result
    
    async def _process_tiktok_photo(
        self,
        url: str,
        context: str,
        resolved_url: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Обрабатывает фото и слайдшоу с TikTok.
        
        Аргументы:
            url: URL контента
            context: Контекст сообщения
            resolved_url: Разрешенный URL
            
        Возвращает:
            Словарь с информацией о медиа или None при ошибке
        """
        target_url = resolved_url or url
        
        # Извлекаем ID из URL
        photo_id_match = re.search(r'/(\d+)[?/]?', target_url)
        photo_id = photo_id_match.group(1) if photo_id_match else "unknown"

        # Основной путь для photo/slideshow: получаем фото и музыку через TikWM.
        tikwm_result = await self._build_from_tikwm_payload(
            target_url=target_url,
            original_url=url,
            context=context,
            photo_id=photo_id,
        )
        if tikwm_result:
            return tikwm_result

        logger.warning("TikWM fallback failed for %s, trying yt-dlp", target_url)

        # Опции для yt-dlp
        ydl_opts = {
            'format': 'bestaudio/best',
            'writethumbnail': False,
            'extract_flat': False,
            'ignoreerrors': True,
            'playlistend': None,
            'extractor_args': {
                'tiktok': {
                    'api_hostname': 'www.tiktok.com',
                    'extract_flat': False,
                    'webpage_fallback': False,
                }
            },
            'force_generic_extractor': False,
        }

        # Скачиваем все медиа
        media_list = await self._download_media_group(
            target_url,
            ydl_opts,
            group_id=photo_id,
            size_limit=self.photo_limit
        )

        # yt-dlp не поддерживает /photo/ URL напрямую, пробуем canonical /video/ как fallback.
        if not media_list and '/photo/' in target_url:
            fallback_url = re.sub(
                r'^https?://(?:m\.)?tiktok\.com',
                'https://www.tiktok.com',
                target_url,
                count=1
            ).replace('/photo/', '/video/', 1)
            logger.warning("Trying ytdlp fallback URL: %s -> %s", target_url, fallback_url)
            media_list = await self._download_media_group(
                fallback_url,
                ydl_opts,
                group_id=photo_id,
                size_limit=self.photo_limit
            )

        if not media_list:
            logger.error("Failed to download media from TikTok post")
            return None

        # Разделяем на фото и аудио
        photos = [m for m in media_list if m['type'] == 'photo']
        audios = [m for m in media_list if m['type'] == 'audio']
        if not photos and not audios:
            logger.error("TikTok photo processing produced no photos and no audio")
            return None

        # Извлекаем информацию из первого файла
        first_info = media_list[0].get('info', {})
        if not isinstance(first_info, dict):
            first_info = {}
        title = first_info.get('title', 'TikTok Photo')
        uploader = first_info.get('uploader', first_info.get('channel', 'Unknown'))

        # Обрабатываем разные сценарии
        if len(photos) == 1 and not audios:
            # Одно фото без аудио
            return {
                'type': 'photo',
                'source_name': 'TikTok',
                'file_path': photos[0]['file_path'],
                'thumbnail_path': None,
                'title': title,
                'uploader': uploader,
                'original_url': url,
                'context': context,
            }
        else:
            # Несколько фото и/или аудио (слайдшоу)
            result = {
                'type': 'media_group',
                'source_name': 'TikTok',
                'files': [{'file_path': p['file_path'], 'type': 'photo'} for p in photos],
                'original_url': url,
                'context': context,
                'title': title,
                'uploader': uploader,
            }
            
            # Добавляем аудио если есть
            if audios:
                music_meta = self._extract_music_metadata_from_info(first_info)
                audio_file = audios[0]['file_path']
                audio_info: Dict[str, Any] = {
                    'file_path': audio_file,
                    'title': music_meta['title'],
                    'performer': music_meta['performer'],
                }
                audio_source_info = audios[0].get('info', {})
                if not isinstance(audio_source_info, dict):
                    audio_source_info = first_info
                music_cover_url = self._extract_music_cover_url_from_info(audio_source_info)
                if music_cover_url:
                    cover_path = self._generate_unique_path(
                        f"{photo_id}_audio_cover",
                        suffix=self._suffix_from_url(music_cover_url, ".jpg"),
                    )
                    if await self._download_thumbnail(music_cover_url, cover_path, size_limit=self.photo_limit):
                        audio_info['thumbnail_path'] = cover_path
                    else:
                        logger.warning("Failed to download ytdlp music cover for %s", target_url)

                result['audio'] = audio_info
                
            return result
