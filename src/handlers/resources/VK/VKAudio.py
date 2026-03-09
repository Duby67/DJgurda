"""
Миксин обработчика VK Music для одиночных аудио-треков.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Sequence
from urllib.parse import urlsplit

import aiofiles
import aiohttp
import yt_dlp
from bs4 import BeautifulSoup

from src.utils.cookies import cleanup_runtime_cookiefile

logger = logging.getLogger(__name__)


class VKAudio:
    """
    Миксин для обработки одиночных треков VK Music.
    """

    def _ensure_vk_runtime_dirs(self) -> None:
        """
        Гарантирует наличие runtime-директории для операций VK.
        """
        try:
            self.temp_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    @classmethod
    def _looks_like_audio_tuple(cls, value: Any) -> bool:
        """
        Проверяет, похож ли объект на tuple-аудио VK.
        """
        if not isinstance(value, list) or len(value) <= cls.AUDIO_INDEX_DURATION:
            return False
        owner_id = cls._safe_int(value[cls.AUDIO_INDEX_OWNER_ID])
        audio_id = cls._safe_int(value[cls.AUDIO_INDEX_ID])
        return owner_id is not None and audio_id is not None

    @classmethod
    def _iter_audio_tuples(cls, value: Any) -> Iterable[list[Any]]:
        """
        Рекурсивно итерирует tuple-аудио из произвольной структуры VK payload.
        """
        if isinstance(value, list):
            if cls._looks_like_audio_tuple(value):
                yield value
                return
            for item in value:
                yield from cls._iter_audio_tuples(item)
            return

        if isinstance(value, dict):
            for nested in value.values():
                yield from cls._iter_audio_tuples(nested)

    def _pick_audio_tuple(
        self,
        payload: Any,
        owner_id: Optional[str] = None,
        audio_id: Optional[str] = None,
    ) -> Optional[list[Any]]:
        """
        Возвращает наиболее подходящий tuple-аудио из payload.
        """
        expected_owner = self._safe_int(owner_id)
        expected_audio = self._safe_int(audio_id)
        fallback: Optional[list[Any]] = None

        for audio_tuple in self._iter_audio_tuples(payload):
            if fallback is None:
                fallback = audio_tuple

            if expected_owner is None or expected_audio is None:
                continue

            tuple_owner = self._safe_int(audio_tuple[self.AUDIO_INDEX_OWNER_ID])
            tuple_audio = self._safe_int(audio_tuple[self.AUDIO_INDEX_ID])
            if tuple_owner == expected_owner and tuple_audio == expected_audio:
                return audio_tuple

        return fallback

    def _extract_cover_url_from_audio_tuple(self, audio_tuple: Sequence[Any]) -> Optional[str]:
        """
        Извлекает URL обложки из tuple-аудио.
        """
        if len(audio_tuple) <= self.AUDIO_INDEX_COVER_URL:
            return None

        raw_cover = audio_tuple[self.AUDIO_INDEX_COVER_URL]
        if isinstance(raw_cover, str):
            for candidate in raw_cover.split(","):
                cleaned = candidate.strip()
                if cleaned.startswith(("http://", "https://")):
                    return cleaned

        return self._extract_first_http_url(raw_cover)

    def _extract_track_metadata_from_audio_tuple(
        self,
        audio_tuple: Sequence[Any],
        canonical_url: str,
    ) -> Dict[str, Any]:
        """
        Преобразует tuple-аудио VK в стандартные метаданные трека.
        """
        title = self._first_non_empty(
            audio_tuple[self.AUDIO_INDEX_TITLE] if len(audio_tuple) > self.AUDIO_INDEX_TITLE else None,
            "VK Music Track",
        ) or "VK Music Track"
        performer = self._first_non_empty(
            audio_tuple[self.AUDIO_INDEX_PERFORMER] if len(audio_tuple) > self.AUDIO_INDEX_PERFORMER else None,
            "Unknown",
        ) or "Unknown"
        duration = self._safe_int(audio_tuple[self.AUDIO_INDEX_DURATION] if len(audio_tuple) > self.AUDIO_INDEX_DURATION else None)
        cover_url = self._extract_cover_url_from_audio_tuple(audio_tuple)

        return {
            "title": title,
            "performer": performer,
            "duration": duration,
            "cover_url": cover_url,
            "canonical_url": canonical_url,
            "source_url": canonical_url,
        }

    def _extract_vk_user_id_from_audio_tuple(self, audio_tuple: Sequence[Any]) -> Optional[int]:
        """
        Извлекает `vk_id` пользователя из tuple-аудио (если доступен).
        """
        if len(audio_tuple) <= 15:
            return None

        payload = audio_tuple[15]
        if isinstance(payload, dict):
            return self._safe_int(payload.get("vk_id"))
        return None

    def _extract_track_metadata(self, html_text: str, canonical_url: str) -> Dict[str, Any]:
        """
        Извлекает метаданные одиночного трека из HTML.
        """
        soup = BeautifulSoup(html_text, "html.parser")
        metadata: Dict[str, Any] = {
            "title": "VK Music Track",
            "performer": "Unknown",
            "duration": None,
            "cover_url": None,
            "canonical_url": canonical_url,
            "source_url": canonical_url,
        }

        for payload in self._extract_ld_objects(html_text):
            payload_type = payload.get("@type")
            type_tokens: set[str] = set()
            if isinstance(payload_type, str):
                type_tokens.add(payload_type.lower())
            elif isinstance(payload_type, list):
                type_tokens.update(
                    item.lower()
                    for item in payload_type
                    if isinstance(item, str)
                )

            if "musicrecording" not in type_tokens and "audioobject" not in type_tokens:
                continue

            metadata["title"] = self._first_non_empty(
                payload.get("name"),
                payload.get("headline"),
                metadata["title"],
            ) or metadata["title"]
            metadata["performer"] = self._first_non_empty(
                self._extract_artist_name(payload.get("byArtist")),
                self._extract_artist_name(payload.get("author")),
                metadata["performer"],
            ) or metadata["performer"]
            metadata["duration"] = (
                self._parse_iso8601_duration(payload.get("duration"))
                or metadata.get("duration")
            )
            metadata["cover_url"] = self._first_non_empty(
                self._extract_first_http_url(payload.get("image")),
                self._extract_first_http_url(payload.get("thumbnailUrl")),
                metadata.get("cover_url"),
            )

        og_title_node = soup.find("meta", attrs={"property": "og:title"})
        og_title = og_title_node.get("content", "") if og_title_node else ""
        if isinstance(og_title, str) and og_title.strip():
            cleaned_title = og_title.replace("| VK", "").strip()
            if " — " in cleaned_title:
                performer, title = cleaned_title.split(" — ", 1)
                metadata["performer"] = self._first_non_empty(performer, metadata["performer"]) or metadata["performer"]
                metadata["title"] = self._first_non_empty(title, metadata["title"]) or metadata["title"]
            elif " - " in cleaned_title:
                performer, title = cleaned_title.split(" - ", 1)
                metadata["performer"] = self._first_non_empty(performer, metadata["performer"]) or metadata["performer"]
                metadata["title"] = self._first_non_empty(title, metadata["title"]) or metadata["title"]
            else:
                metadata["title"] = self._first_non_empty(cleaned_title, metadata["title"]) or metadata["title"]

        og_image_node = soup.find("meta", attrs={"property": "og:image"})
        og_image = og_image_node.get("content", "") if og_image_node else ""
        if isinstance(og_image, str) and og_image.startswith(("http://", "https://")):
            metadata["cover_url"] = metadata.get("cover_url") or og_image

        duration_meta_node = soup.find("meta", attrs={"property": "music:duration:seconds"})
        duration_meta = duration_meta_node.get("content", "") if duration_meta_node else ""
        metadata["duration"] = self._safe_int(duration_meta) or metadata.get("duration")

        return metadata

    @classmethod
    def _is_audio_media_url(cls, url: str) -> bool:
        """
        Проверяет, похож ли URL на валидный источник аудио.
        """
        if not isinstance(url, str):
            return False
        lowered = url.lower()
        if not lowered.startswith(("http://", "https://")):
            return False
        if "audio_api_unavailable" in lowered:
            return False
        if any(ext in lowered for ext in cls.AUDIO_EXTENSIONS):
            return True
        if ".m3u8" in lowered:
            return True
        return "vkuseraudio.net" in lowered or ("userapi.com" in lowered and "/audio/" in lowered)

    @classmethod
    def _score_audio_url(cls, url: str) -> int:
        """
        Эвристика качества URL аудио.
        """
        lowered = url.lower()
        score = 0
        if ".mp3" in lowered:
            score += 40
        if ".m4a" in lowered:
            score += 30
        if "extra=" in lowered:
            score += 10
        if "index.m3u8" in lowered:
            score -= 50
        if "audio_api_unavailable" in lowered:
            score -= 100
        return score

    def _extract_audio_url_from_html(self, html_text: str) -> Optional[str]:
        """
        Извлекает direct URL аудио-трека из HTML.
        """
        candidates: list[str] = []
        for pattern in self.AUDIO_URL_PATTERNS:
            for match in pattern.finditer(html_text):
                raw_url = match.group("url")
                decoded_url = self._decode_escaped_url(raw_url)
                if self._is_audio_media_url(decoded_url):
                    candidates.append(decoded_url)

        if not candidates:
            return None

        unique_candidates = list(dict.fromkeys(candidates))
        return max(unique_candidates, key=self._score_audio_url)

    def _vk_base64_decode(self, value: str) -> Optional[str]:
        """
        Декодирует VK-строку из кастомного base64-алфавита.
        """
        if not value or len(value) % 4 == 1:
            return None

        decoded_chars: list[str] = []
        buffer = 0
        processed = 0

        for char in value:
            char_index = self.VK_AUDIO_B64_ALPHABET.find(char)
            if char_index == -1:
                continue

            buffer = 64 * buffer + char_index if processed % 4 else char_index
            prev_processed = processed
            processed += 1

            if prev_processed % 4:
                decoded_chars.append(chr(255 & (buffer >> ((-2 * processed) & 6))))

        return "".join(decoded_chars)

    @staticmethod
    def _vk_build_permutation(length: int, seed: int) -> list[int]:
        """
        Строит permutation-массив для операции shuffle в VK-декодере.
        """
        if length <= 0:
            return []

        current_seed = abs(int(seed))
        permutation = [0] * length
        for index in range(length - 1, -1, -1):
            current_seed = (length * (index + 1) ^ current_seed + index) % length
            permutation[index] = current_seed

        return permutation

    def _vk_shuffle(self, value: str, seed: int) -> str:
        """
        Выполняет VK shuffle-операцию над строкой.
        """
        size = len(value)
        if size == 0:
            return value

        permutation = self._vk_build_permutation(size, seed)
        chars = list(value)
        for index in range(1, size):
            swap_index = permutation[size - 1 - index]
            chars[index], chars[swap_index] = chars[swap_index], chars[index]

        return "".join(chars)

    def _vk_decode_audio_url(self, encoded_url: str, vk_user_id: Optional[int] = None) -> str:
        """
        Декодирует `audio_api_unavailable` URL в рабочий HTTP URL.
        """
        if "audio_api_unavailable" not in encoded_url or "?extra=" not in encoded_url:
            return encoded_url

        extra_payload = encoded_url.split("?extra=", 1)[1]
        if "#" in extra_payload:
            main_part, operations_part = extra_payload.split("#", 1)
        else:
            main_part, operations_part = extra_payload, ""

        decoded_url = self._vk_base64_decode(main_part)
        decoded_operations = "" if operations_part == "" else self._vk_base64_decode(operations_part)

        if not decoded_url or not isinstance(decoded_operations, str):
            return encoded_url

        operations = decoded_operations.split(self.VK_OP_SEPARATOR) if decoded_operations else []
        current_value = decoded_url
        user_id = vk_user_id if vk_user_id is not None else self._vk_user_id

        for raw_operation in reversed(operations):
            if not raw_operation:
                continue

            parts = raw_operation.split(self.VK_ARG_SEPARATOR)
            operation_name = parts[0] if parts else ""
            operation_args = parts[1:] if len(parts) > 1 else []

            if operation_name == "v":
                current_value = current_value[::-1]
                continue

            if operation_name == "r":
                shift = self._safe_int(operation_args[0] if operation_args else None)
                if shift is None:
                    return encoded_url
                chars = list(current_value)
                doubled_alphabet = self.VK_AUDIO_B64_ALPHABET + self.VK_AUDIO_B64_ALPHABET
                for index in range(len(chars) - 1, -1, -1):
                    alphabet_index = doubled_alphabet.find(chars[index])
                    if alphabet_index != -1:
                        chars[index] = doubled_alphabet[alphabet_index - shift]
                current_value = "".join(chars)
                continue

            if operation_name == "s":
                seed = self._safe_int(operation_args[0] if operation_args else None)
                if seed is None:
                    return encoded_url
                current_value = self._vk_shuffle(current_value, seed)
                continue

            if operation_name == "i":
                seed = self._safe_int(operation_args[0] if operation_args else None)
                if seed is None or user_id is None:
                    return encoded_url
                current_value = self._vk_shuffle(current_value, user_id ^ seed)
                continue

            if operation_name == "x":
                if not operation_args or not operation_args[0]:
                    return encoded_url
                xor_char = operation_args[0][0]
                current_value = "".join(chr(ord(char) ^ ord(xor_char)) for char in current_value)
                continue

            return encoded_url

        return current_value if current_value.startswith("http") else encoded_url

    async def _download_audio_hls_with_ytdlp(
        self,
        hls_url: str,
        track_token: str,
    ) -> Optional[Path]:
        """
        Скачивает HLS-аудио через yt-dlp (без использования как основного extractor).
        """
        self._ensure_vk_runtime_dirs()
        base_path = self._generate_unique_path(track_token, suffix="")
        output_template = f"{base_path}.%(ext)s"

        ydl_opts: Dict[str, Any] = self._build_ytdlp_opts({
            "noplaylist": True,
            "format": "bestaudio/best",
            "retries": 2,
            "fragment_retries": 2,
            "concurrent_fragment_downloads": 4,
            "outtmpl": output_template,
            "http_headers": {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "ru,en-US;q=0.9,en;q=0.8",
            },
        })
        cookiefile_path = ydl_opts.get("cookiefile")

        def _download() -> Optional[Path]:
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(hls_url, download=True)
                    if not isinstance(info, dict):
                        return None
                    return Path(ydl.prepare_filename(info))
            finally:
                cleanup_runtime_cookiefile(cookiefile_path)

        try:
            downloaded_path = await asyncio.to_thread(_download)
        except Exception as exc:
            logger.warning("VK HLS download failed for %s: %s", hls_url, exc)
            return None

        if isinstance(downloaded_path, Path) and downloaded_path.exists():
            final_path = downloaded_path
        else:
            candidates = sorted(
                self.temp_dir.glob(f"{base_path.name}.*"),
                key=lambda item: item.stat().st_mtime if item.exists() else 0,
                reverse=True,
            )
            final_path = next((candidate for candidate in candidates if candidate.exists()), None)

        if not isinstance(final_path, Path) or not final_path.exists():
            return None

        file_size = final_path.stat().st_size
        if file_size <= 0 or file_size > self.audio_limit:
            final_path.unlink(missing_ok=True)
            return None

        return final_path

    async def _extract_audio_url_with_ytdlp_fallback(self, url: str) -> Optional[str]:
        """
        Редкий fallback: пытается извлечь direct URL через yt-dlp metadata режим.
        """
        ydl_opts: Dict[str, Any] = self._build_ytdlp_opts({
            "skip_download": True,
            "geo_bypass": True,
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        })
        ydl_opts.update(self._build_vk_cookie_opts())
        cookiefile_path = ydl_opts.get("cookiefile")
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await asyncio.to_thread(ydl.extract_info, url, download=False)
            if not isinstance(info, dict):
                return None

            direct_url = info.get("url")
            if isinstance(direct_url, str) and self._is_audio_media_url(direct_url):
                return direct_url

            formats = info.get("formats")
            if isinstance(formats, list):
                for fmt in formats:
                    if not isinstance(fmt, dict):
                        continue
                    fmt_url = fmt.get("url")
                    if isinstance(fmt_url, str) and self._is_audio_media_url(fmt_url):
                        return fmt_url
        except Exception as exc:
            logger.warning("VK yt-dlp fallback failed for %s: %s", url, exc)
        finally:
            cleanup_runtime_cookiefile(cookiefile_path)
        return None

    async def _download_audio_stream(
        self,
        session: aiohttp.ClientSession,
        audio_url: str,
        track_token: str,
    ) -> Optional[Path]:
        """
        Скачивает аудио по direct URL.
        """
        lowered = audio_url.lower()
        if ".m3u8" in lowered:
            hls_path = await self._download_audio_hls_with_ytdlp(audio_url, track_token=track_token)
            if hls_path:
                return hls_path

        self._ensure_vk_runtime_dirs()
        path_suffix = Path(urlsplit(audio_url).path).suffix.lower()
        suffix = path_suffix if path_suffix in self.AUDIO_EXTENSIONS else ".mp3"
        file_path = self._generate_unique_path(track_token, suffix=suffix)

        try:
            async with session.get(
                audio_url,
                allow_redirects=True,
                cookies=self._request_cookies or None,
            ) as response:
                if response.status != 200:
                    logger.warning("VK audio download failed (%s): %s", response.status, audio_url)
                    return None

                content_length = self._safe_int(response.headers.get("Content-Length"))
                if content_length and content_length > self.audio_limit:
                    logger.warning("VK audio exceeds configured size limit: %s bytes", content_length)
                    return None

                total_size = 0
                async with aiofiles.open(file_path, "wb") as file_obj:
                    async for chunk in response.content.iter_chunked(128 * 1024):
                        if not chunk:
                            continue
                        total_size += len(chunk)
                        if total_size > self.audio_limit:
                            logger.warning("VK audio exceeds configured size limit during stream.")
                            file_path.unlink(missing_ok=True)
                            return None
                        await file_obj.write(chunk)

            if not file_path.exists() or file_path.stat().st_size <= 0:
                file_path.unlink(missing_ok=True)
                return None
            return file_path

        except Exception as exc:
            logger.warning("VK audio download failed for %s: %s", audio_url, exc)
            file_path.unlink(missing_ok=True)
            return None

    @classmethod
    def _build_track_candidates(cls, owner_id: str, audio_id: str, access_hash: Optional[str]) -> tuple[str, ...]:
        """
        Возвращает VK URL-кандидаты трека для web/mobile extraction.
        """
        token = cls._build_track_token(owner_id, audio_id, access_hash)
        return (f"https://vk.com/audio{token}",)

    async def _fetch_audio_tuple_via_reload_audios(
        self,
        session: aiohttp.ClientSession,
        owner_id: str,
        audio_id: str,
        access_hash: Optional[str],
    ) -> Optional[list[Any]]:
        """
        Получает tuple-аудио через `al_audio.php?act=reload_audios`.
        """
        candidate_ids = [
            self._build_track_token(owner_id, audio_id, access_hash),
            f"{owner_id}_{audio_id}",
        ]

        seen_ids: set[str] = set()
        for audio_ids in candidate_ids:
            if audio_ids in seen_ids:
                continue
            seen_ids.add(audio_ids)

            response = await self._post_json(
                session,
                "https://vk.com/al_audio.php?act=reload_audios",
                {
                    "al": "1",
                    "audio_ids": audio_ids,
                },
            )
            if not response:
                continue

            payload = response.get("payload")
            audio_tuple = self._pick_audio_tuple(payload, owner_id=owner_id, audio_id=audio_id)
            if audio_tuple:
                return audio_tuple

        return None

    def _audio_tuple_to_track_preview(self, audio_tuple: Sequence[Any]) -> Dict[str, Any]:
        """
        Преобразует tuple-аудио в metadata-трек для playlist preview.
        """
        owner = self._safe_int(audio_tuple[self.AUDIO_INDEX_OWNER_ID] if len(audio_tuple) > self.AUDIO_INDEX_OWNER_ID else None)
        audio = self._safe_int(audio_tuple[self.AUDIO_INDEX_ID] if len(audio_tuple) > self.AUDIO_INDEX_ID else None)
        access_key = self._first_non_empty(
            audio_tuple[self.AUDIO_INDEX_ACCESS_KEY] if len(audio_tuple) > self.AUDIO_INDEX_ACCESS_KEY else None,
        )

        canonical_track_url = None
        if owner is not None and audio is not None:
            canonical_track_url = self._build_track_canonical_url(str(owner), str(audio), access_key)

        return {
            "title": self._first_non_empty(
                audio_tuple[self.AUDIO_INDEX_TITLE] if len(audio_tuple) > self.AUDIO_INDEX_TITLE else None,
                "VK Track",
            )
            or "VK Track",
            "performer": self._first_non_empty(
                audio_tuple[self.AUDIO_INDEX_PERFORMER] if len(audio_tuple) > self.AUDIO_INDEX_PERFORMER else None,
                "Unknown",
            )
            or "Unknown",
            "duration": self._safe_int(audio_tuple[self.AUDIO_INDEX_DURATION] if len(audio_tuple) > self.AUDIO_INDEX_DURATION else None),
            "source_url": canonical_track_url,
            "canonical_url": canonical_track_url,
            "cover_url": self._extract_cover_url_from_audio_tuple(audio_tuple),
        }

    async def _process_vk_audio(
        self,
        session: aiohttp.ClientSession,
        original_url: str,
        context: str,
        owner_id: str,
        audio_id: str,
        access_hash: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        """
        Обрабатывает одиночный трек VK Music.
        """
        track_token = self._build_track_token(owner_id, audio_id, access_hash)
        canonical_url = self._build_track_canonical_url(owner_id, audio_id, access_hash)
        metadata: Dict[str, Any] = {
            "title": "VK Music Track",
            "performer": "Unknown",
            "duration": None,
            "cover_url": None,
            "canonical_url": canonical_url,
            "source_url": canonical_url,
        }

        best_audio_url: Optional[str] = None
        best_html: Optional[str] = None
        tuple_vk_user_id: Optional[int] = None

        api_audio_tuple = await self._fetch_audio_tuple_via_reload_audios(
            session=session,
            owner_id=owner_id,
            audio_id=audio_id,
            access_hash=access_hash,
        )
        if api_audio_tuple:
            metadata.update(self._extract_track_metadata_from_audio_tuple(api_audio_tuple, canonical_url=canonical_url))
            tuple_vk_user_id = self._extract_vk_user_id_from_audio_tuple(api_audio_tuple)

            raw_audio_url = self._first_non_empty(
                api_audio_tuple[self.AUDIO_INDEX_URL] if len(api_audio_tuple) > self.AUDIO_INDEX_URL else None,
            )
            if raw_audio_url:
                decoded_audio_url = self._decode_escaped_url(raw_audio_url)
                decoded_audio_url = self._vk_decode_audio_url(decoded_audio_url, vk_user_id=tuple_vk_user_id)
                if self._is_audio_media_url(decoded_audio_url):
                    best_audio_url = decoded_audio_url

        candidate_urls = self._build_track_candidates(owner_id, audio_id, access_hash)
        html_audio_url: Optional[str] = None
        for candidate_url in candidate_urls:
            html_text = await self._fetch_html(session, candidate_url)
            if not html_text:
                continue
            if not best_html:
                best_html = html_text

            extracted_audio_url = self._extract_audio_url_from_html(html_text)
            if not extracted_audio_url:
                continue

            decoded_audio_url = self._vk_decode_audio_url(
                self._decode_escaped_url(extracted_audio_url),
                vk_user_id=tuple_vk_user_id,
            )
            if not self._is_audio_media_url(decoded_audio_url):
                continue

            html_audio_url = decoded_audio_url
            best_html = html_text
            break

        if best_html:
            html_metadata = self._extract_track_metadata(best_html, canonical_url=canonical_url)

            current_title = str(metadata.get("title") or "").strip()
            if not current_title or current_title in {"VK Music Track", "VK Track"}:
                metadata["title"] = self._first_non_empty(html_metadata.get("title"), current_title, "VK Music Track")

            current_performer = str(metadata.get("performer") or "").strip()
            if not current_performer or current_performer == "Unknown":
                metadata["performer"] = self._first_non_empty(html_metadata.get("performer"), current_performer, "Unknown")

            if metadata.get("duration") is None:
                metadata["duration"] = self._safe_int(html_metadata.get("duration"))

            if not metadata.get("cover_url"):
                metadata["cover_url"] = self._first_non_empty(html_metadata.get("cover_url"))

        if not best_audio_url and html_audio_url:
            best_audio_url = html_audio_url

        if not best_audio_url:
            fallback_audio_url = await self._extract_audio_url_with_ytdlp_fallback(canonical_url)
            if isinstance(fallback_audio_url, str):
                fallback_audio_url = self._vk_decode_audio_url(
                    self._decode_escaped_url(fallback_audio_url),
                    vk_user_id=tuple_vk_user_id,
                )
                if self._is_audio_media_url(fallback_audio_url):
                    best_audio_url = fallback_audio_url
                    logger.warning("VK audio direct URL extracted via yt-dlp fallback for %s", canonical_url)

        if not best_audio_url:
            logger.error("VK audio stream URL not found for %s", canonical_url)
            return None

        file_path = await self._download_audio_stream(session, best_audio_url, track_token=track_token)
        if not file_path:
            logger.error("VK audio download failed for %s", canonical_url)
            return None

        self._ensure_vk_runtime_dirs()
        cover_path: Optional[Path] = None
        cover_url = metadata.get("cover_url")
        if isinstance(cover_url, str) and cover_url.startswith(("http://", "https://")):
            cover_path = self._generate_unique_path(f"{track_token}_cover", suffix=".jpg")
            if not await self._download_thumbnail(cover_url, cover_path, self.photo_limit):
                cover_path = None

        return {
            "type": "audio",
            "source_name": self.source_name,
            "file_path": file_path,
            "thumbnail_path": cover_path,
            "title": metadata.get("title") or "VK Music Track",
            "uploader": metadata.get("performer") or "Unknown",
            "duration": metadata.get("duration"),
            "source_url": original_url,
            "canonical_url": canonical_url,
            "original_url": original_url,
            "context": context,
            "metadata": {
                "cover_url": metadata.get("cover_url"),
                "audio_url": best_audio_url,
            },
        }
