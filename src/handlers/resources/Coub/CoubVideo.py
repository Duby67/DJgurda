"""
Обработчик видео-контента COUB.
"""

import asyncio
import aiohttp
import logging
import re

from pathlib import Path
from shutil import which
from typing import Any, Dict, Iterable, Optional, Tuple
from urllib.parse import urlsplit

from src.handlers.mixins import VideoMixin

logger = logging.getLogger(__name__)


class CoubVideo(VideoMixin):
    """
    Миксин для обработки видео из COUB.
    """

    COUB_ID_PATTERN = re.compile(r"/view/([A-Za-z0-9]+)")
    COUB_METADATA_API_URL_TEMPLATE = "https://coub.com/api/v2/coubs/{coub_id}.json"
    COUB_SEGMENTS_API_URL_TEMPLATE = "https://coub.com/api/v2/coubs/{coub_id}/segments"
    VIDEO_EXTENSIONS = frozenset({".mp4", ".m4v", ".mov", ".webm"})
    AUDIO_EXTENSIONS = frozenset({".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wav"})
    IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".gif"})

    async def _fetch_json_payload(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Запрашивает JSON payload по URL.
        """
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
        }
        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        logger.warning("COUB API HTTP %s for %s", response.status, url)
                        return None
                    payload = await response.json(content_type=None)
                    if not isinstance(payload, dict):
                        logger.warning("COUB API returned invalid payload for %s", url)
                        return None
                    return payload
        except Exception as exc:
            logger.warning("COUB API request failed for %s: %s", url, exc)
            return None

    @staticmethod
    def _first_http_url(value: Any) -> Optional[str]:
        """
        Возвращает первый HTTP(S) URL из произвольной структуры.
        """
        if isinstance(value, str):
            return value if value.startswith(("http://", "https://")) else None

        if isinstance(value, (list, tuple)):
            for item in value:
                found = CoubVideo._first_http_url(item)
                if found:
                    return found
            return None

        if isinstance(value, dict):
            for nested in value.values():
                found = CoubVideo._first_http_url(nested)
                if found:
                    return found
            return None

        return None

    @staticmethod
    def _collect_http_urls(value: Any) -> Iterable[str]:
        """
        Итерирует все HTTP(S) URL из произвольной структуры.
        """
        if isinstance(value, str):
            if value.startswith(("http://", "https://")):
                yield value
            return

        if isinstance(value, (list, tuple)):
            for item in value:
                yield from CoubVideo._collect_http_urls(item)
            return

        if isinstance(value, dict):
            for nested in value.values():
                yield from CoubVideo._collect_http_urls(nested)

    @staticmethod
    def _collect_http_urls_with_key_path(
        value: Any,
        key_path: tuple[str, ...] = (),
    ) -> Iterable[Tuple[str, tuple[str, ...]]]:
        """
        Итерирует все HTTP(S) URL вместе с путём ключей до найденного значения.
        """
        if isinstance(value, str):
            if value.startswith(("http://", "https://")):
                yield value, key_path
            return

        if isinstance(value, (list, tuple)):
            for item in value:
                yield from CoubVideo._collect_http_urls_with_key_path(item, key_path)
            return

        if isinstance(value, dict):
            for key, nested in value.items():
                yield from CoubVideo._collect_http_urls_with_key_path(
                    nested,
                    (*key_path, str(key).lower()),
                )

    @staticmethod
    def _deduplicate_urls(urls: Iterable[str]) -> list[str]:
        """
        Убирает дубликаты URL с сохранением порядка.
        """
        unique_urls: list[str] = []
        seen: set[str] = set()
        for raw_url in urls:
            candidate = raw_url.strip()
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            unique_urls.append(candidate)
        return unique_urls

    @staticmethod
    def _is_valid_media_url(url: str) -> bool:
        """
        Проверяет, что URL выглядит как валидный медиа-URL, а не заглушка.
        """
        lowered = url.lower()
        if "/missing/missing.png" in lowered:
            return False
        return lowered.startswith(("http://", "https://"))

    def _classify_media_url(self, url: str) -> Optional[str]:
        """
        Классифицирует URL как video/audio/None.
        """
        if not self._is_valid_media_url(url):
            return None

        path = urlsplit(url).path.lower()
        ext = Path(path).suffix.lower()

        if ext in self.IMAGE_EXTENSIONS:
            return None
        if ext in self.VIDEO_EXTENSIONS:
            return "video"
        if ext in self.AUDIO_EXTENSIONS:
            return "audio"

        # Нечеткая классификация для URL без расширения.
        if "audio" in path:
            return "audio"
        if "video" in path and "image" not in path:
            return "video"
        return None

    @staticmethod
    def _score_url(url: str) -> int:
        """
        Возвращает эвристику качества URL по его имени.
        """
        lowered = url.lower()
        score = 0
        if "high" in lowered or "big" in lowered or "hd" in lowered:
            score += 40
        if "raw" in lowered or "original" in lowered:
            score += 35
        if "med" in lowered or "medium" in lowered:
            score += 20
        if "low" in lowered:
            score += 10
        if "muted" in lowered:
            score -= 5
        if "share" in lowered:
            score -= 10
        if "watermark" in lowered or "branded" in lowered or "logo" in lowered:
            score -= 50
        return score

    def _pick_best_url(self, urls: Iterable[str]) -> Optional[str]:
        """
        Выбирает лучший URL по эвристике качества.
        """
        valid_urls = [url for url in urls if self._is_valid_media_url(url)]
        if not valid_urls:
            return None
        return max(valid_urls, key=self._score_url)

    def _order_urls_by_quality(self, urls: Iterable[str]) -> list[str]:
        """
        Упорядочивает URL по приоритету качества с удалением дублей.
        """
        valid_urls = [url for url in urls if self._is_valid_media_url(url)]
        return sorted(self._deduplicate_urls(valid_urls), key=self._score_url, reverse=True)

    @staticmethod
    def _infer_media_type_from_key_path(key_path: tuple[str, ...]) -> Optional[str]:
        """
        Пытается определить тип медиа по пути ключей в JSON.
        """
        if not key_path:
            return None

        combined = "/".join(part.lower() for part in key_path)
        if any(token in combined for token in ("image", "thumbnail", "poster", "preview")):
            return None
        if any(token in combined for token in ("audio", "sound", "music", "voice")):
            return "audio"
        if any(token in combined for token in ("video", "clip", "movie", "mp4", "webm")):
            return "video"
        return None

    @staticmethod
    def _nested_get(data: Dict[str, Any], *keys: str) -> Any:
        """
        Безопасно получает вложенное значение из словаря.
        """
        current: Any = data
        for key in keys:
            if not isinstance(current, dict):
                return None
            current = current.get(key)
        return current

    def _extract_metadata_source_urls(self, metadata: Dict[str, Any]) -> Dict[str, list[str] | Optional[str]]:
        """
        Извлекает source URL из metadata COUB.
        """
        file_versions = metadata.get("file_versions")
        if not isinstance(file_versions, dict):
            file_versions = {}

        video_urls_raw: list[str] = []
        audio_urls_raw: list[str] = []

        video_candidates = (
            self._nested_get(file_versions, "html5", "video", "high", "url"),
            self._nested_get(file_versions, "html5", "video", "med", "url"),
            self._nested_get(file_versions, "iphone", "url"),
            self._nested_get(file_versions, "mobile", "video"),
            self._nested_get(file_versions, "mobile", "video_url"),
        )
        for candidate in video_candidates:
            found = self._first_http_url(candidate)
            if isinstance(found, str):
                video_urls_raw.append(found)

        audio_candidates = (
            self._nested_get(file_versions, "html5", "audio", "high", "url"),
            self._nested_get(file_versions, "html5", "audio", "med", "url"),
            self._nested_get(file_versions, "mobile", "audio_url"),
            self._nested_get(file_versions, "mobile", "audio"),
            metadata.get("audio_file_url"),
        )
        for candidate in audio_candidates:
            if isinstance(candidate, list):
                for item in candidate:
                    found = self._first_http_url(item)
                    if isinstance(found, str):
                        audio_urls_raw.append(found)
                continue

            found = self._first_http_url(candidate)
            if isinstance(found, str):
                audio_urls_raw.append(found)

        share_url = self._first_http_url(self._nested_get(file_versions, "share", "default"))

        return {
            "video_urls": self._deduplicate_urls(video_urls_raw),
            "audio_urls": self._deduplicate_urls(audio_urls_raw),
            "share_url": share_url if isinstance(share_url, str) else None,
        }

    def _extract_segment_source_urls(self, segments_payload: Dict[str, Any]) -> Tuple[list[str], list[str]]:
        """
        Извлекает video/audio URL из payload endpoint /segments.
        """
        video_urls: list[str] = []
        audio_urls: list[str] = []

        candidate_nodes: list[Any] = []
        segments = segments_payload.get("segments")
        if isinstance(segments, list):
            candidate_nodes.extend(segments)
        elif isinstance(segments, dict):
            candidate_nodes.append(segments)
        else:
            candidate_nodes.append(segments_payload)

        for node in candidate_nodes:
            for candidate_url, key_path in self._collect_http_urls_with_key_path(node):
                media_type = self._classify_media_url(candidate_url)
                if not media_type:
                    media_type = self._infer_media_type_from_key_path(key_path)

                if media_type == "video":
                    video_urls.append(candidate_url)
                elif media_type == "audio":
                    audio_urls.append(candidate_url)

        for candidate_url in self._deduplicate_urls(self._collect_http_urls(segments_payload)):
            if candidate_url in video_urls or candidate_url in audio_urls:
                continue
            media_type = self._classify_media_url(candidate_url)
            if media_type == "video":
                video_urls.append(candidate_url)
            elif media_type == "audio":
                audio_urls.append(candidate_url)

        return self._deduplicate_urls(video_urls), self._deduplicate_urls(audio_urls)

    @staticmethod
    def _url_suffix(url: str, default_suffix: str) -> str:
        """
        Возвращает расширение файла по URL.
        """
        suffix = Path(urlsplit(url).path).suffix.lower()
        return suffix if suffix else default_suffix

    async def _download_url_to_file(self, source_url: str, target_path: Path) -> bool:
        """
        Скачивает бинарный файл по прямому URL.
        """
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }
        try:
            timeout = aiohttp.ClientTimeout(total=90)
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                async with session.get(source_url) as response:
                    if response.status != 200:
                        logger.warning("Direct media download HTTP %s for %s", response.status, source_url)
                        return False
                    with target_path.open("wb") as file_obj:
                        async for chunk in response.content.iter_chunked(256 * 1024):
                            if not chunk:
                                continue
                            file_obj.write(chunk)
            return target_path.exists() and target_path.stat().st_size > 0
        except Exception as exc:
            logger.warning("Direct media download failed for %s: %s", source_url, exc)
            return False

    @staticmethod
    async def _run_ffmpeg_command(command: list[str]) -> Tuple[bool, str]:
        """
        Запускает ffmpeg-команду и возвращает результат выполнения.
        """
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        error_text = stderr.decode(errors="ignore").strip() if stderr else ""
        return process.returncode == 0, error_text

    async def _mux_video_and_audio(self, video_path: Path, audio_path: Path, output_path: Path) -> bool:
        """
        Объединяет видео и аудио в MP4.
        Длительность результата всегда выравнивается по аудио:
        видеоряд зацикливается, пока не закончится аудиодорожка.
        """
        ffmpeg_path = which("ffmpeg")
        if not ffmpeg_path:
            return False

        audio_suffix = audio_path.suffix.lower()
        copy_audio = audio_suffix in {".aac", ".m4a"}

        copy_command = [
            ffmpeg_path,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-stream_loop",
            "-1",
            "-i",
            str(video_path),
            "-i",
            str(audio_path),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-shortest",
            "-fflags",
            "+genpts",
            "-movflags",
            "+faststart",
        ]
        if copy_audio:
            copy_command.extend(["-c:a", "copy"])
        else:
            copy_command.extend(["-c:a", "aac", "-b:a", "192k"])
        copy_command.append(str(output_path))

        copy_ok, copy_error = await self._run_ffmpeg_command(copy_command)
        if copy_ok:
            return output_path.exists() and output_path.stat().st_size > 0

        output_path.unlink(missing_ok=True)

        # Fallback: если stream-copy не сработал, перекодируем видео,
        # но сохраняем логику audio-led по длительности.
        reencode_command = [
            ffmpeg_path,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-stream_loop",
            "-1",
            "-i",
            str(video_path),
            "-i",
            str(audio_path),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-shortest",
            "-movflags",
            "+faststart",
        ]
        if copy_audio:
            reencode_command.extend(["-c:a", "copy"])
        else:
            reencode_command.extend(["-c:a", "aac", "-b:a", "192k"])
        reencode_command.append(str(output_path))

        reencode_ok, reencode_error = await self._run_ffmpeg_command(reencode_command)
        if not reencode_ok:
            logger.warning(
                "ffmpeg mux failed for %s + %s (copy error: %s, reencode error: %s)",
                video_path,
                audio_path,
                copy_error or "unknown error",
                reencode_error or "unknown error",
            )
            return False
        return output_path.exists() and output_path.stat().st_size > 0

    async def _build_video_with_audio(
        self,
        *,
        video_url: str,
        audio_url: str,
        video_id: str,
    ) -> Optional[Path]:
        """
        Скачивает video/audio по прямым URL и собирает единый MP4.
        """
        video_tmp = self._generate_unique_path(f"{video_id}_video", suffix=self._url_suffix(video_url, ".mp4"))
        audio_tmp = self._generate_unique_path(f"{video_id}_audio", suffix=self._url_suffix(audio_url, ".m4a"))
        output_path = self._generate_unique_path(video_id, suffix=".mp4")

        try:
            if not await self._download_url_to_file(video_url, video_tmp):
                return None
            if not await self._download_url_to_file(audio_url, audio_tmp):
                return None
            if not await self._mux_video_and_audio(video_tmp, audio_tmp, output_path):
                return None
            if output_path.stat().st_size > self.video_limit:
                logger.warning("COUB merged video is too large (%s bytes)", output_path.stat().st_size)
                output_path.unlink(missing_ok=True)
                return None
            return output_path
        finally:
            video_tmp.unlink(missing_ok=True)
            audio_tmp.unlink(missing_ok=True)

    @staticmethod
    def _build_file_info(
        *,
        file_path: Path,
        title: str,
        uploader: str,
        original_url: str,
        context: str,
    ) -> Dict[str, Any]:
        """
        Формирует итоговый file_info для pipeline отправки.
        """
        return {
            "type": "video",
            "source_name": "COUB",
            "file_path": file_path,
            "thumbnail_path": None,
            "title": title,
            "uploader": uploader,
            "original_url": original_url,
            "context": context,
        }

    @staticmethod
    def _extract_uploader(metadata: Dict[str, Any]) -> str:
        """
        Возвращает имя автора из metadata COUB.
        """
        channel = metadata.get("channel")
        if isinstance(channel, dict):
            title = channel.get("title")
            if isinstance(title, str) and title.strip():
                return title.strip()

        uploader = metadata.get("uploader")
        if isinstance(uploader, str) and uploader.strip():
            return uploader.strip()

        return "Unknown"

    async def _try_source_segments(
        self,
        *,
        coub_id: str,
        segment_video_urls: list[str],
        ordered_audio_urls: list[str],
    ) -> Optional[Path]:
        """
        SOURCE A: segments (приоритетный путь для минимизации watermark).
        """
        if not segment_video_urls:
            logger.info("COUB segments source has no usable video for %s", coub_id)
            return None

        if not ordered_audio_urls:
            logger.info("COUB segments source is incomplete for %s (video/audio pair not found)", coub_id)
            return None

        if not which("ffmpeg"):
            logger.warning("ffmpeg is not available; COUB segments source cannot be muxed for %s", coub_id)
            return None

        ordered_video_urls = self._order_urls_by_quality(segment_video_urls)
        for video_url in ordered_video_urls:
            for audio_url in ordered_audio_urls:
                merged_path = await self._build_video_with_audio(
                    video_url=video_url,
                    audio_url=audio_url,
                    video_id=f"{coub_id}_segments",
                )
                if merged_path:
                    return merged_path
        return None

    async def _try_source_share(
        self,
        *,
        coub_id: str,
        metadata_urls: Dict[str, list[str] | Optional[str]],
        ordered_audio_urls: list[str],
    ) -> Optional[Path]:
        """
        SOURCE B: file_versions.share.default.
        """
        share_url = metadata_urls.get("share_url")
        if not isinstance(share_url, str) or not self._is_valid_media_url(share_url):
            return None

        if ordered_audio_urls and which("ffmpeg"):
            for audio_url in ordered_audio_urls:
                merged_path = await self._build_video_with_audio(
                    video_url=share_url,
                    audio_url=audio_url,
                    video_id=f"{coub_id}_share_muxed",
                )
                if merged_path:
                    return merged_path

        result = await self._download_video(
            share_url,
            {
                "format": "best[ext=mp4]/best",
                "writethumbnail": False,
                "noplaylist": True,
            },
            video_id=f"{coub_id}_share",
        )
        if not result:
            return None
        return result["file_path"]

    async def _try_source_file_versions(
        self,
        *,
        coub_id: str,
        metadata_urls: Dict[str, list[str] | Optional[str]],
        ordered_audio_urls: list[str],
    ) -> Optional[Path]:
        """
        SOURCE C: html5/mobile/iphone + fallback на текущий ytdlp-style.
        """
        video_urls = [url for url in metadata_urls.get("video_urls", []) if isinstance(url, str)]

        if video_urls and ordered_audio_urls and which("ffmpeg"):
            ordered_video_urls = self._order_urls_by_quality(video_urls)

            for video_url in ordered_video_urls:
                for audio_url in ordered_audio_urls:
                    merged_path = await self._build_video_with_audio(
                        video_url=video_url,
                        audio_url=audio_url,
                        video_id=f"{coub_id}_fallback",
                    )
                    if merged_path:
                        return merged_path

        # Последний fallback: текущий ytdlp-style по основной ссылке COUB.
        has_ffmpeg = bool(which("ffmpeg"))
        ydl_result = await self._download_video(
            f"https://www.coub.com/view/{coub_id}",
            {
                "format": (
                    "html5-video-high+html5-audio-high/"
                    "html5-video-high+html5-audio-med/"
                    "bestvideo+bestaudio/best"
                    if has_ffmpeg
                    else "best[ext=mp4]/best"
                ),
                "writethumbnail": False,
                "noplaylist": True,
                "merge_output_format": "mp4",
            },
            video_id=f"{coub_id}_ytdlp",
        )
        if ydl_result:
            return ydl_result["file_path"]

        return None

    async def _process_coub_video(
        self,
        url: str,
        context: str,
        original_url: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Скачивает COUB-видео и возвращает структуру для дальнейшей отправки.
        """
        coub_match = self.COUB_ID_PATTERN.search(url)
        coub_id = coub_match.group(1) if coub_match else self._extract_video_id(url)

        metadata_url = self.COUB_METADATA_API_URL_TEMPLATE.format(coub_id=coub_id)
        metadata = await self._fetch_json_payload(metadata_url)
        if not metadata:
            logger.error("COUB metadata is unavailable for %s", coub_id)
            return None

        permalink = metadata.get("permalink")
        if not isinstance(permalink, str) or permalink.lower() != coub_id.lower():
            logger.error(
                "COUB permalink mismatch detected: requested=%s, returned=%s",
                coub_id,
                permalink,
            )
            return None

        title_raw = metadata.get("title")
        title = title_raw.strip() if isinstance(title_raw, str) and title_raw.strip() else "COUB Video"
        uploader = self._extract_uploader(metadata)
        metadata_urls = self._extract_metadata_source_urls(metadata)
        metadata_audio_urls = [url for url in metadata_urls.get("audio_urls", []) if isinstance(url, str)]

        segments_url = self.COUB_SEGMENTS_API_URL_TEMPLATE.format(coub_id=coub_id)
        segments_payload = await self._fetch_json_payload(segments_url)
        segment_video_urls: list[str] = []
        segment_audio_urls: list[str] = []
        if segments_payload:
            segment_video_urls, segment_audio_urls = self._extract_segment_source_urls(segments_payload)

        ordered_audio_urls = self._order_urls_by_quality([*segment_audio_urls, *metadata_audio_urls])
        if not ordered_audio_urls:
            logger.warning("COUB has no explicit audio source URLs for %s", coub_id)

        # SOURCE A: segments (приоритет no-watermark).
        file_path = await self._try_source_segments(
            coub_id=coub_id,
            segment_video_urls=segment_video_urls,
            ordered_audio_urls=ordered_audio_urls,
        )
        if file_path:
            return self._build_file_info(
                file_path=file_path,
                title=title,
                uploader=uploader,
                original_url=original_url,
                context=context,
            )

        # SOURCE B: share.
        file_path = await self._try_source_share(
            coub_id=coub_id,
            metadata_urls=metadata_urls,
            ordered_audio_urls=ordered_audio_urls,
        )
        if file_path:
            return self._build_file_info(
                file_path=file_path,
                title=title,
                uploader=uploader,
                original_url=original_url,
                context=context,
            )

        # SOURCE C: file_versions/html5/mobile/iphone + ytdlp-style fallback.
        file_path = await self._try_source_file_versions(
            coub_id=coub_id,
            metadata_urls=metadata_urls,
            ordered_audio_urls=ordered_audio_urls,
        )
        if file_path:
            return self._build_file_info(
                file_path=file_path,
                title=title,
                uploader=uploader,
                original_url=original_url,
                context=context,
            )

        logger.error("COUB download pipeline exhausted for %s: no usable source found", coub_id)
        return None
