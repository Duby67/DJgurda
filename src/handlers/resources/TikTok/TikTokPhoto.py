"""
Обработчик фото и слайдшоу TikTok.
"""

import re
import logging
from typing import Optional, Dict, Any

from src.handlers.mixins import PhotoMixin, MediaGroupMixin

logger = logging.getLogger(__name__)

class TikTokPhoto(PhotoMixin, MediaGroupMixin):
    """
    Миксин для обработки фото и слайдшоу TikTok.
    """
    
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

        if not media_list:
            logger.error("Не удалось скачать медиа из поста TikTok")
            return None

        # Разделяем на фото и аудио
        photos = [m for m in media_list if m['type'] == 'photo']
        audios = [m for m in media_list if m['type'] == 'audio']

        # Извлекаем информацию из первого файла
        first_info = media_list[0]['info']
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
                audio_file = audios[0]['file_path']
                result['audio'] = {
                    'file_path': audio_file,
                    'title': title,
                    'performer': uploader,
                }
                
            return result
