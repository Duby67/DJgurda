import yt_dlp
import asyncio
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

from .base import BaseMixin

logger = logging.getLogger(__name__)

class MediaGroupMixin(BaseMixin):
    """
    Миксин для скачивания группы медиафайлов (например, несколько фото + аудио) из одного URL.
    Использует yt-dlp для извлечения всех доступных форматов.
    """
    async def _download_media_group(
        self,
        url: str,
        ydl_opts: dict,
        group_id: str = None,
        size_limit: int = None
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Скачивает все доступные медиафайлы из URL (например, слайд-шоу TikTok).
        Возвращает список словарей с ключами:
            - file_path (Path): путь к скачанному файлу
            - type (str): 'photo', 'audio' или 'video'
            - info (dict): информация об этом конкретном файле от yt-dlp (опционально)
        """
        if size_limit is None:
            # По умолчанию используем лимит для видео (максимальный), но можно передать другой
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
            'ignoreerrors': True,          # Продолжать при ошибках загрузки отдельных элементов
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

                # Собираем все скачанные файлы
                if 'requested_downloads' in info and info['requested_downloads']:
                    # Несколько файлов (плейлист или мультиформат)
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
                                    media_type = 'video'  # например .mp4
                                downloaded_files.append({
                                    'file_path': file_path,
                                    'type': media_type,
                                    'info': entry
                                })
                            else:
                                logger.warning(f"Файл {file_path} превышает лимит ({file_size} > {size_limit}), удаляем")
                                file_path.unlink(missing_ok=True)
                else:
                    # Один файл (возможно, обычное видео или фото)
                    file_path = Path(ydl.prepare_filename(info))
                    if not file_path.exists():
                        # Попробуем найти по шаблону
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

        except Exception as e:
            logger.exception(f"Ошибка при скачивании медиа-группы: {e}")
            # Удаляем уже скачанные файлы
            for fp in file_paths_to_cleanup:
                if fp.exists():
                    fp.unlink(missing_ok=True)
            return None