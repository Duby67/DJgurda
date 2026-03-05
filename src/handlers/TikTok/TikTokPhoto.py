import re
import logging
from typing import Optional, Dict, Any, List

from src.handlers.mixins import PhotoMixin, MediaGroupMixin

logger = logging.getLogger(__name__)

class TikTokPhoto(PhotoMixin, MediaGroupMixin):
    """
    Миксин для обработки фото и слайд-шоу TikTok.
    Использует MediaGroupMixin для скачивания нескольких фото и аудио.
    """
    async def _extract_photo_info(self, url: str) -> Optional[Dict]:
        # Оставляем старый метод на случай, если понадобится,
        # но для слайд-шоу он не нужен.
        # Можно удалить, если не используется.
        pass

    async def _process_tiktok_photo(
        self,
        url: str,
        context: str,
        resolved_url: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        target_url = resolved_url or url
        photo_id_match = re.search(r'/(\d+)[?/]?', target_url)
        photo_id = photo_id_match.group(1) if photo_id_match else "unknown"

        # Опции для yt-dlp: хотим получить все изображения и аудио
        ydl_opts = {
            'format': 'bestaudio/best',
            'writethumbnail': False,
            'extract_flat': False,
            'ignoreerrors': True,
            'playlistend': None,
            'extractor_args': {
                'tiktok': {
                    'api_hostname': 'www.tiktok.com',
                    'extract_flat': False,  # важно для получения всех элементов
                    'webpage_fallback': False,  # не падать на веб-страницу
                }
            },
            # Пробуем принудительно указать extractor
            'force_generic_extractor': False,  # не использовать generic
        }
        # Для TikTok, возможно, нужно указать extractor_args, но обычно yt-dlp сам определяет.

        # Скачиваем все медиа
        media_list = await self._download_media_group(
            target_url,
            ydl_opts,
            group_id=photo_id,
            size_limit=self.photo_limit  # используем лимит для фото (для аудио потом отдельно)
        )

        if not media_list:
            logger.error("Не удалось скачать медиа из поста")
            return None

        # Разделяем на фото и аудио
        photos = [m for m in media_list if m['type'] == 'photo']
        audios = [m for m in media_list if m['type'] == 'audio']

        # Извлекаем общую информацию из первого файла (если доступна)
        first_info = media_list[0]['info']
        title = first_info.get('title', 'TikTok Photo')
        uploader = first_info.get('uploader', first_info.get('channel', 'Unknown'))

        if len(photos) == 1 and not audios:
            # Одно фото, без аудио
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
            # Несколько фото и/или аудио
            result = {
                'type': 'media_group',
                'source_name': 'TikTok',
                'files': [{'file_path': p['file_path'], 'type': 'photo'} for p in photos],
                'original_url': url,
                'context': context,
                'title': title,
                'uploader': uploader,
            }
            if audios:
                # Берём первое аудио (обычно одно)
                audio_file = audios[0]['file_path']
                result['audio'] = {
                    'file_path': audio_file,
                    'title': title,
                    'performer': uploader,
                }
            return result