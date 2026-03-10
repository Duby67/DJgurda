"""
Composition-based инфраструктурные сервисы для media runtime.

Модуль предоставляет явные сервисы для stable runtime handlers
без множественного наследования gateway-классов от mixins.
"""

from __future__ import annotations

import asyncio
import logging
import random
import uuid
from pathlib import Path
from typing import Any, Iterable, Optional

import aiofiles
import aiohttp
import yt_dlp

from src.config import AUDIO_SIZE_LIMIT, PHOTO_SIZE_LIMIT, VIDEO_SIZE_LIMIT
from src.utils.cookies import cleanup_runtime_cookiefile

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


class _YtdlpQuietLogger:
    """
    Тихий logger для yt-dlp, перенаправляющий сообщения в debug-уровень.
    """

    def __init__(self, scope: str) -> None:
        self._scope = scope

    def debug(self, message: str) -> None:
        logger.debug("%s yt-dlp: %s", self._scope, message)

    def info(self, message: str) -> None:
        logger.debug("%s yt-dlp: %s", self._scope, message)

    def warning(self, message: str) -> None:
        logger.debug("%s yt-dlp warning: %s", self._scope, message)

    def error(self, message: str) -> None:
        logger.debug("%s yt-dlp error: %s", self._scope, message)


class RuntimePathService:
    """
    Сервис runtime-путей: идентификаторы и уникальные пути временных файлов.
    """

    def __init__(self, runtime_dir: Path) -> None:
        self.runtime_dir = runtime_dir
        self.runtime_dir.mkdir(parents=True, exist_ok=True)

    def generate_unique_path(self, identifier: str, *, suffix: str = "") -> Path:
        """
        Генерирует уникальный путь во временной runtime-директории.
        """
        # Runtime-директория может быть очищена lifecycle-обслуживанием.
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        unique_id = f"{identifier}_{uuid.uuid4().hex[:8]}"
        return self.runtime_dir / f"{unique_id}{suffix}"

    @staticmethod
    def extract_video_id(url: str) -> str:
        """
        Извлекает последний сегмент URL как идентификатор медиа.
        """
        parts = url.rstrip("/").split("/")
        return parts[-1].split("?")[0]


class DelayPolicyService:
    """
    Сервис случайной задержки между сетевыми запросами.
    """

    async def random_delay(self, *, min_sec: float = 1, max_sec: float = 3) -> None:
        """
        Выполняет случайную задержку в заданном диапазоне.
        """
        delay = random.uniform(min_sec, max_sec)
        logger.debug("Waiting %.2f seconds", delay)
        await asyncio.sleep(delay)


class YtdlpOptionBuilder:
    """
    Сервис сборки опций yt-dlp с тихим логированием.
    """

    def __init__(self, *, scope: str) -> None:
        self._scope = scope

    def build(
        self,
        default_opts: dict[str, Any],
        ydl_opts: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        Объединяет дефолтные и внешние опции yt-dlp.
        """
        merged_opts: dict[str, Any] = dict(default_opts)
        if ydl_opts:
            merged_opts.update(ydl_opts)
        merged_opts.setdefault("quiet", True)
        merged_opts.setdefault("no_warnings", True)
        merged_opts.setdefault("logger", _YtdlpQuietLogger(self._scope))
        return merged_opts


class YtdlpVideoService:
    """
    Сервис загрузки видео через yt-dlp.
    """

    def __init__(
        self,
        *,
        runtime_paths: RuntimePathService,
        delay_policy: DelayPolicyService,
        option_builder: YtdlpOptionBuilder,
        video_limit: int = VIDEO_SIZE_LIMIT,
    ) -> None:
        self._runtime_paths = runtime_paths
        self._delay_policy = delay_policy
        self._option_builder = option_builder
        self.video_limit = video_limit

    @staticmethod
    def _is_format_unavailable_error(exc: Exception) -> bool:
        """
        Проверяет, относится ли ошибка к недоступному формату.
        """
        message = str(exc).lower()
        return (
            "requested format is not available" in message
            or "format is not available" in message
        )

    async def download_video(
        self,
        url: str,
        ydl_opts: dict[str, Any],
        *,
        video_id: Optional[str] = None,
        size_limit: Optional[int] = None,
        allow_format_fallback: bool = True,
        cleanup_cookiefile: bool = True,
    ) -> Optional[dict[str, Any]]:
        """
        Скачивает видео и возвращает payload с путями/метаданными.
        """
        if size_limit is None:
            size_limit = self.video_limit

        await self._delay_policy.random_delay()

        if video_id is None:
            video_id = self._runtime_paths.extract_video_id(url)
        base_path = self._runtime_paths.generate_unique_path(video_id)

        default_opts = {
            "outtmpl": str(base_path),
            "user_agent": DEFAULT_USER_AGENT,
            "geo_bypass": True,
        }
        merged_opts = self._option_builder.build(default_opts, ydl_opts)
        cookiefile_path = merged_opts.get("cookiefile")

        file_path: Path | None = None
        thumb_path: Path | None = None

        try:
            with yt_dlp.YoutubeDL(merged_opts) as ydl:
                info = await asyncio.to_thread(ydl.extract_info, url, download=True)
                if not info:
                    logger.error("Failed to get video information")
                    return None

                if "requested_downloads" in info:
                    downloaded_file = info["requested_downloads"][0]["filepath"]
                else:
                    downloaded_file = ydl.prepare_filename(info)
                file_path = Path(downloaded_file)

                if not file_path.exists():
                    candidates = list(self._runtime_paths.runtime_dir.glob(f"{base_path.stem}*"))
                    if candidates:
                        file_path = candidates[0]
                    else:
                        logger.error("File not found: %s", file_path)
                        return None

                file_size = file_path.stat().st_size
                if file_size > size_limit:
                    logger.warning("Video is too large (%s bytes). Removing.", file_size)
                    file_path.unlink(missing_ok=True)
                    return None

                for ext in [".jpg", ".webp", ".png"]:
                    thumb_candidate = file_path.with_suffix(ext)
                    if thumb_candidate.exists():
                        thumb_path = thumb_candidate
                        break

                return {
                    "file_path": file_path,
                    "thumbnail_path": thumb_path,
                    "info": info,
                }

        except Exception as exc:
            if allow_format_fallback and self._is_format_unavailable_error(exc):
                current_format = ydl_opts.get("format")
                if isinstance(current_format, str) and current_format.strip() != "best":
                    logger.warning(
                        "Requested format unavailable for %s; retrying with fallback format=best",
                        url,
                    )
                    fallback_opts = {**ydl_opts, "format": "best"}
                    return await self.download_video(
                        url=url,
                        ydl_opts=fallback_opts,
                        video_id=video_id,
                        size_limit=size_limit,
                        allow_format_fallback=False,
                        cleanup_cookiefile=False,
                    )

            logger.exception("Failed to download video: %s", exc)
            if file_path and file_path.exists():
                file_path.unlink(missing_ok=True)
            if thumb_path and thumb_path.exists():
                thumb_path.unlink(missing_ok=True)
            return None
        finally:
            if cleanup_cookiefile:
                cleanup_runtime_cookiefile(cookiefile_path)


class YtdlpMetadataService:
    """
    Сервис извлечения метаданных через yt-dlp без скачивания медиа.
    """

    def __init__(
        self,
        *,
        delay_policy: DelayPolicyService,
        option_builder: YtdlpOptionBuilder,
    ) -> None:
        self._delay_policy = delay_policy
        self._option_builder = option_builder

    async def extract_metadata(
        self,
        url: str,
        ydl_opts: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        """
        Извлекает метаданные URL.
        """
        default_opts = {
            "skip_download": True,
            "user_agent": DEFAULT_USER_AGENT,
            "geo_bypass": True,
        }
        merged_opts = self._option_builder.build(default_opts, ydl_opts)
        cookiefile_path = merged_opts.get("cookiefile")

        await self._delay_policy.random_delay()

        try:
            with yt_dlp.YoutubeDL(merged_opts) as ydl:
                info = await asyncio.to_thread(ydl.extract_info, url, download=False)
            if not isinstance(info, dict):
                logger.warning("Metadata extraction returned invalid payload for %s", url)
                return None
            return info
        except Exception as exc:
            logger.exception("Failed to extract metadata for %s: %s", url, exc)
            return None
        finally:
            cleanup_runtime_cookiefile(cookiefile_path)

    @staticmethod
    def _extract_first_http_url(value: Any) -> Optional[str]:
        """
        Ищет первый HTTP(S) URL в произвольной структуре.
        """
        if isinstance(value, str):
            return value if value.startswith(("http://", "https://")) else None

        if isinstance(value, (list, tuple)):
            for item in value:
                found = YtdlpMetadataService._extract_first_http_url(item)
                if found:
                    return found
            return None

        if isinstance(value, dict):
            for nested_value in value.values():
                found = YtdlpMetadataService._extract_first_http_url(nested_value)
                if found:
                    return found
            return None

        return None

    def pick_thumbnail_url(
        self,
        info: dict[str, Any],
        *,
        candidate_keys: Iterable[str],
    ) -> Optional[str]:
        """
        Выбирает первый валидный URL миниатюры.
        """
        for key in candidate_keys:
            if key not in info:
                continue
            found = self._extract_first_http_url(info.get(key))
            if found:
                return found
        return None


class YtdlpMediaGroupService:
    """
    Сервис загрузки media_group через yt-dlp.
    """

    def __init__(
        self,
        *,
        runtime_paths: RuntimePathService,
        delay_policy: DelayPolicyService,
        option_builder: YtdlpOptionBuilder,
        default_size_limit: int = VIDEO_SIZE_LIMIT,
    ) -> None:
        self._runtime_paths = runtime_paths
        self._delay_policy = delay_policy
        self._option_builder = option_builder
        self._default_size_limit = default_size_limit

    async def download_media_group(
        self,
        url: str,
        ydl_opts: dict[str, Any],
        *,
        group_id: Optional[str] = None,
        size_limit: Optional[int] = None,
    ) -> Optional[list[dict[str, Any]]]:
        """
        Скачивает все доступные элементы группы медиа.
        """
        if size_limit is None:
            size_limit = self._default_size_limit

        await self._delay_policy.random_delay()

        if group_id is None:
            group_id = self._runtime_paths.extract_video_id(url)
        base_path = self._runtime_paths.generate_unique_path(group_id)

        default_opts = {
            # Уникальный шаблон имени предотвращает перезапись карусельных файлов.
            "outtmpl": str(base_path.with_name(f"{base_path.stem}_%(autonumber)03d.%(ext)s")),
            "user_agent": DEFAULT_USER_AGENT,
            "geo_bypass": True,
            "ignoreerrors": True,
        }
        merged_opts = self._option_builder.build(default_opts, ydl_opts)
        cookiefile_path = merged_opts.get("cookiefile")

        downloaded_files: list[dict[str, Any]] = []
        file_paths_to_cleanup: list[Path] = []

        try:
            with yt_dlp.YoutubeDL(merged_opts) as ydl:
                info = await asyncio.to_thread(ydl.extract_info, url, download=True)
                if not info:
                    logger.error("Failed to get media group information")
                    return None

                info_nodes: list[dict[str, Any]] = []
                if isinstance(info, dict):
                    info_nodes.append(info)
                    entries = info.get("entries")
                    if isinstance(entries, list):
                        info_nodes.extend([entry for entry in entries if isinstance(entry, dict)])

                candidate_files: list[tuple[Path, dict[str, Any]]] = []
                for node in info_nodes:
                    requested_downloads = node.get("requested_downloads")
                    if isinstance(requested_downloads, list):
                        for request_item in requested_downloads:
                            if not isinstance(request_item, dict):
                                continue
                            filepath = request_item.get("filepath")
                            if isinstance(filepath, str):
                                candidate_files.append((Path(filepath), node))

                    try:
                        prepared = ydl.prepare_filename(node)
                        if isinstance(prepared, str):
                            candidate_files.append((Path(prepared), node))
                    except Exception:
                        continue

                for path in self._runtime_paths.runtime_dir.glob(f"{base_path.stem}_*"):
                    if path.is_file():
                        candidate_files.append((path, info if isinstance(info, dict) else {}))

                seen_paths: set[str] = set()
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
                    if ext in [".jpg", ".jpeg", ".png", ".webp"]:
                        media_type = "photo"
                    elif ext in [".mp3", ".m4a", ".aac", ".ogg"]:
                        media_type = "audio"
                    else:
                        media_type = "video"

                    downloaded_files.append(
                        {
                            "file_path": file_path,
                            "type": media_type,
                            "info": source_info if isinstance(source_info, dict) else info,
                        }
                    )

                if not downloaded_files:
                    logger.error("Failed to download any files")
                    return None

                return downloaded_files

        except Exception as exc:
            logger.exception("Failed to download media group: %s", exc)
            for file_path in file_paths_to_cleanup:
                if file_path.exists():
                    file_path.unlink(missing_ok=True)
            return None
        finally:
            cleanup_runtime_cookiefile(cookiefile_path)


class HttpFileService:
    """
    Сервис загрузки бинарных файлов (photo/audio/thumbnail) через aiohttp.
    """

    def __init__(
        self,
        *,
        delay_policy: DelayPolicyService,
        photo_limit: int = PHOTO_SIZE_LIMIT,
        audio_limit: int = AUDIO_SIZE_LIMIT,
    ) -> None:
        self._delay_policy = delay_policy
        self.photo_limit = photo_limit
        self.audio_limit = audio_limit

    async def _download_file(
        self,
        url: str,
        dest_path: Path,
        *,
        headers: Optional[dict[str, str]] = None,
        timeout: Optional[int] = None,
    ) -> bool:
        """
        Базовая загрузка файла по URL.
        """
        try:
            async with aiohttp.ClientSession() as session:
                request_timeout = timeout if timeout is not None else aiohttp.ClientTimeout(total=None)
                async with session.get(url, headers=headers, timeout=request_timeout) as response:
                    if response.status != 200:
                        logger.error("Failed to download %s: HTTP %s", url, response.status)
                        return False

                    async with aiofiles.open(dest_path, "wb") as file_obj:
                        await file_obj.write(await response.read())
            return True
        except Exception as exc:
            logger.exception("Download error for %s: %s", url, exc)
            return False

    async def download_photo(
        self,
        image_url: str,
        dest_path: Path,
        *,
        size_limit: Optional[int] = None,
    ) -> bool:
        """
        Скачивает изображение с проверкой лимита.
        """
        if size_limit is None:
            size_limit = self.photo_limit

        await self._delay_policy.random_delay()

        success = await self._download_file(
            image_url,
            dest_path,
            headers={"User-Agent": DEFAULT_USER_AGENT},
            timeout=10,
        )
        if not success:
            return False

        file_size = dest_path.stat().st_size
        if file_size > size_limit:
            logger.warning("Photo is too large (%s bytes). Removing.", file_size)
            dest_path.unlink(missing_ok=True)
            return False
        return True

    async def download_audio(
        self,
        url: str,
        dest_path: Path,
        *,
        size_limit: Optional[int] = None,
    ) -> bool:
        """
        Скачивает аудиофайл с проверкой лимита.
        """
        if size_limit is None:
            size_limit = self.audio_limit

        await self._delay_policy.random_delay()

        success = await self._download_file(url, dest_path)
        if not success:
            return False

        file_size = dest_path.stat().st_size
        if file_size > size_limit:
            logger.warning("Audio file is too large (%s bytes). Removing.", file_size)
            dest_path.unlink(missing_ok=True)
            return False
        return True

    async def download_thumbnail(
        self,
        url: str,
        dest_path: Path,
        *,
        size_limit: Optional[int] = None,
    ) -> bool:
        """
        Скачивает миниатюру/обложку с проверкой лимита.
        """
        if size_limit is None:
            size_limit = self.photo_limit

        await self._delay_policy.random_delay()

        success = await self._download_file(url, dest_path)
        if not success:
            return False

        file_size = dest_path.stat().st_size
        if file_size > size_limit:
            logger.warning("Cover image is too large (%s bytes). Removing.", file_size)
            dest_path.unlink(missing_ok=True)
            return False
        return True
