"""
Миксин для обработки групп медиа (несколько фото + аудио).

Используется для загрузки слайд-шоу и других составных медиа-форматов.
"""

import yt_dlp
import asyncio
import logging

from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import BaseMixin

logger = logging.getLogger(__name__)


class MediaGroupMixin(BaseMixin):
    """
    Миксин для скачивания групп медиафайлов через yt-dlp.
    """
    
    async def _download_media_group(
        self,
        url: str,
        ydl_opts: Dict[str, Any],
        group_id: Optional[str] = None,
        size_limit: Optional[int] = None
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Скачивает все доступные медиафайлы из URL (например, слайд-шоу TikTok).
        
        Args:
            url: URL медиа-группы
            ydl_opts: Опции для yt-dlp
            group_id: Идентификатор группы (опционально)
            size_limit: Лимит размера файла в байтах
            
        Returns:
            Список словарей с информацией о файлах или None при ошибке
        """
        if size_limit is None:
            size_limit = getattr(self, 'video_limit', 50 * 1024 * 1024)

        await self._random_delay()

        if group_id is None:
            group_id = self._extract_video_id(url)
        base_path = self._generate_unique_path(group_id)

        default_opts = {
            'outtmpl': str(base_path),
            'quiet': True,
            'no_warnings': True,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'geo_bypass': True,
            'ignoreerrors': True,  # Продолжать при ошибках загрузки отдельных элементов
        }
        merged_opts = {**default_opts, **ydl_opts}

        downloaded_files = []
        file_paths_to_cleanup = []  # для удаления в случае ошибки

        try:
            with yt_dlp.YoutubeDL(merged_opts) as ydl:
                info = await asyncio.to_thread(ydl.extract_info, url, download=True)
                if not info:
                    logger.error("Не удалось получить информацию о медиа-группе")
                    return None

                # Обрабатываем несколько файлов (плейлист или мультиформат)
                if 'requested_downloads' in info and info['requested_downloads']:
                    for entry in info['requested_downloads']:
                        file_path = Path(entry['filepath'])
                        if file_path.exists():
                            file_paths_to_cleanup.append(file_path)
                            file_size = file_path.stat().st_size
                            
                            if file_size <= size_limit:
                                # Определяем тип по расширению
                                ext = file_path.suffix.lower()
                                if ext in ['.jpg', '.jpeg', '.png', '.webp']:
                                    media_type = 'photo'
                                elif ext in ['.mp3', '.m4a', '.aac', '.ogg']:
                                    media_type = 'audio'
                                else:
                                    media_type = 'video'
                                    
                                downloaded_files.append({
                                    'file_path': file_path,
                                    'type': media_type,
                                    'info': entry
                                })
                            else:
                                logger.warning(f"Файл {file_path} превышает лимит ({file_size} > {size_limit}), удаляем")
                                file_path.unlink(missing_ok=True)
                else:
                    # Обрабатываем один файл
                    file_path = Path(ydl.prepare_filename(info))
                    if not file_path.exists():
                        # Ищем альтернативные пути
                        candidates = list(self.temp_dir.glob(f"{base_path.stem}*"))
                        if candidates:
                            file_path = candidates[0]
                        else:
                            logger.error(f"Файл не найден: {file_path}")
                            return None

                    file_paths_to_cleanup.append(file_path)
                    file_size = file_path.stat().st_size
                    
                    if file_size <= size_limit:
                        ext = file_path.suffix.lower()
                        if ext in ['.jpg', '.jpeg', '.png', '.webp']:
                            media_type = 'photo'
                        elif ext in ['.mp3', '.m4a', '.aac']:
                            media_type = 'audio'
                        else:
                            media_type = 'video'
                            
                        downloaded_files.append({
                            'file_path': file_path,
                            'type': media_type,
                            'info': info
                        })
                    else:
                        logger.warning(f"Файл {file_path} превышает лимит, удаляем")
                        file_path.unlink(missing_ok=True)

                if not downloaded_files:
                    logger.error("Не удалось скачать ни одного файла")
                    return None

                return downloaded_files

        except Exception as exc:
            logger.exception("Ошибка при скачивании медиа-группы: %s", exc)
            # Очищаем временные файлы при ошибке
            for file_path in file_paths_to_cleanup:
                if file_path.exists():
                    file_path.unlink(missing_ok=True)
            return None
