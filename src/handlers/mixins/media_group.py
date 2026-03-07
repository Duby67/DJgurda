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
        
        Аргументы:
            url: URL медиа-группы
            ydl_opts: Опции для yt-dlp
            group_id: Идентификатор группы (опционально)
            size_limit: Лимит размера файла в байтах
            
        Возвращает:
            Список словарей с информацией о файлах или None при ошибке
        """
        if size_limit is None:
            size_limit = getattr(self, 'video_limit', 50 * 1024 * 1024)

        await self._random_delay()

        if group_id is None:
            group_id = self._extract_video_id(url)
        base_path = self._generate_unique_path(group_id)

        default_opts = {
            # Уникальный шаблон имени, чтобы элементы карусели не перезаписывали друг друга.
            'outtmpl': str(base_path.with_name(f"{base_path.stem}_%(autonumber)03d.%(ext)s")),
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
                    logger.error("Failed to get media group information")
                    return None

                # Собираем кандидатов файлов из структуры yt-dlp (включая entries).
                info_nodes: list[Dict[str, Any]] = []
                if isinstance(info, dict):
                    info_nodes.append(info)
                    entries = info.get("entries")
                    if isinstance(entries, list):
                        info_nodes.extend([entry for entry in entries if isinstance(entry, dict)])

                candidate_files: list[tuple[Path, Dict[str, Any]]] = []
                for node in info_nodes:
                    requested_downloads = node.get("requested_downloads")
                    if isinstance(requested_downloads, list):
                        for request_item in requested_downloads:
                            if not isinstance(request_item, dict):
                                continue
                            filepath = request_item.get("filepath")
                            if isinstance(filepath, str):
                                candidate_files.append((Path(filepath), node))

                    # fallback: пытаемся вычислить ожидаемое имя.
                    try:
                        prepared = ydl.prepare_filename(node)
                        if isinstance(prepared, str):
                            candidate_files.append((Path(prepared), node))
                    except Exception:
                        continue

                # Дополнительный fallback: все файлы текущей загрузки по префиксу.
                for path in self.temp_dir.glob(f"{base_path.stem}_*"):
                    if path.is_file():
                        candidate_files.append((path, info if isinstance(info, dict) else {}))

                seen_paths = set()
                for file_path, source_info in candidate_files:
                    resolved = str(file_path.resolve()) if file_path.exists() else str(file_path)
                    if resolved in seen_paths:
                        continue
                    seen_paths.add(resolved)

                    if not file_path.exists():
                        continue

                    file_paths_to_cleanup.append(file_path)
                    file_size = file_path.stat().st_size
                    if file_size > size_limit:
                        logger.warning(
                            "File %s exceeds size limit (%s > %s), removing",
                            file_path,
                            file_size,
                            size_limit,
                        )
                        file_path.unlink(missing_ok=True)
                        continue

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
                        'info': source_info if isinstance(source_info, dict) else info
                    })

                if not downloaded_files:
                    logger.error("Failed to download any files")
                    return None

                return downloaded_files

        except Exception as exc:
            logger.exception("Failed to download media group: %s", exc)
            # Очищаем временные файлы при ошибке
            for file_path in file_paths_to_cleanup:
                if file_path.exists():
                    file_path.unlink(missing_ok=True)
            return None
