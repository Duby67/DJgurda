"""
Главный обработчик VK Music (audio + playlist).
"""

from __future__ import annotations

import asyncio
import html
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Sequence, Tuple
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

import aiofiles
import aiohttp
import yt_dlp
from bs4 import BeautifulSoup

from src.config import VK_COOKIES, VK_COOKIES_ENABLED
from src.handlers.base import BaseHandler
from src.handlers.mixins import AudioMixin
from src.utils.cookies import build_request_cookies

logger = logging.getLogger(__name__)


class VKHandler(BaseHandler, AudioMixin):
    """
    Асинхронный обработчик VK Music:
    - одиночный трек (`audio`);
    - плейлист (`playlist`).
    """

    PATTERN = re.compile(
        r"https?://(?:www\.|m\.)?(?:vk\.com|vk\.ru)/"
        r"(?:audio-?\d+_\d+(?:_[A-Za-z0-9]+)?|music/playlist/-?\d+_\d+(?:_[A-Za-z0-9]+)?)"
        r"(?:/?(?:\?.*)?)?$",
        re.IGNORECASE,
    )
    TRACK_PATH_PATTERN = re.compile(
        r"^audio(?P<owner>-?\d+)_(?P<audio>\d+)(?:_(?P<access_hash>[A-Za-z0-9]+))?/?$",
        re.IGNORECASE,
    )
    PLAYLIST_PATH_PATTERN = re.compile(
        r"^music/playlist/(?P<owner>-?\d+)_(?P<playlist>\d+)(?:_(?P<access_hash>[A-Za-z0-9]+))?/?$",
        re.IGNORECASE,
    )
    TRACKING_QUERY_PARAMS = frozenset(
        {
            "from",
            "w",
            "z",
            "utm_source",
            "utm_medium",
            "utm_campaign",
            "utm_term",
            "utm_content",
        }
    )
    AUDIO_EXTENSIONS = frozenset({".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".mp4"})
    AUDIO_URL_PATTERNS = (
        re.compile(
            r'"(?:url|play_url|audio_url|stream_url|mp3|src)"\s*:\s*"(?P<url>https?:\\\\/\\\\/[^"]+)"',
            re.IGNORECASE,
        ),
        re.compile(
            r"(?P<url>https?:\\\\u002F\\\\u002F[^\"'\\\s<>]+)",
            re.IGNORECASE,
        ),
        re.compile(
            r"(?P<url>https?:\\\\/\\\\/[^\"'\\\s<>]+\.(?:mp3|m4a|aac|ogg|opus|wav|m3u8|mp4)[^\"'\\\s<>]*)",
            re.IGNORECASE,
        ),
        re.compile(
            r"(?P<url>https?://[^\"'\\\s<>]+\.(?:mp3|m4a|aac|ogg|opus|wav|m3u8|mp4)[^\"'\\\s<>]*)",
            re.IGNORECASE,
        ),
    )
    TRACK_LINK_PATTERN = re.compile(
        r"/audio(?P<owner>-?\d+)_(?P<audio>\d+)(?:_(?P<access_hash>[A-Za-z0-9]+))?",
        re.IGNORECASE,
    )
    TRACK_COUNT_PATTERNS = (
        re.compile(r'"tracksCount"\s*:\s*(\d+)', re.IGNORECASE),
        re.compile(r'"track_count"\s*:\s*(\d+)', re.IGNORECASE),
        re.compile(r"(\d+)\s+трек", re.IGNORECASE),
    )
    AUDIO_INDEX_ID = 0
    AUDIO_INDEX_OWNER_ID = 1
    AUDIO_INDEX_URL = 2
    AUDIO_INDEX_TITLE = 3
    AUDIO_INDEX_PERFORMER = 4
    AUDIO_INDEX_DURATION = 5
    AUDIO_INDEX_HASHES = 13
    AUDIO_INDEX_COVER_URL = 14
    AUDIO_INDEX_ACCESS_KEY = 24
    VK_AUDIO_B64_ALPHABET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMN0PQRSTUVWXYZO123456789+/="
    VK_OP_SEPARATOR = chr(9)
    VK_ARG_SEPARATOR = chr(11)
    VK_PLAYLIST_CONTEXT = "audio_page"
    VK_MAX_PLAYLIST_PAGES = 20

    def __init__(self) -> None:
        """
        Инициализирует обработчик и заранее подгружает cookies (если доступны).
        """
        super().__init__()
        self._request_cookies = build_request_cookies(
            provider_key="vk",
            provider_name="VK",
            enabled=VK_COOKIES_ENABLED,
            cookie_path=VK_COOKIES,
            path_env_name="VK_COOKIES_PATH",
            log=logger,
        )
        self._vk_user_id = self._safe_int(self._request_cookies.get("remixuserid")) or 0
        self._badbrowser_logged_pairs: set[tuple[str, str]] = set()

    @property
    def pattern(self) -> re.Pattern:
        """
        Возвращает паттерн распознавания VK URL.
        """
        return self.PATTERN

    @property
    def source_name(self) -> str:
        """
        Возвращает имя источника.
        """
        return "VK"

    @staticmethod
    def _first_non_empty(*values: Any) -> Optional[str]:
        """
        Возвращает первую непустую строку.
        """
        for value in values:
            if isinstance(value, str):
                cleaned = value.strip()
                if cleaned:
                    return cleaned
        return None

    @staticmethod
    def _safe_int(value: Any) -> Optional[int]:
        """
        Безопасно преобразует значение в int.
        """
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            cleaned = value.strip()
            if re.match(r"^-?\d+$", cleaned):
                return int(cleaned)
        return None

    @staticmethod
    def _decode_escaped_url(raw_url: str) -> str:
        """
        Приводит escaped-URL из HTML/JSON к обычному виду.
        """
        decoded = html.unescape(raw_url.strip().strip('"').strip("'"))
        replacements = (
            ("\\u002F", "/"),
            ("\\u003A", ":"),
            ("\\u0026", "&"),
            ("\\u003D", "="),
            ("\\u0025", "%"),
            ("\\/", "/"),
        )
        for source, target in replacements:
            decoded = decoded.replace(source, target)
        return unquote(decoded)

    @staticmethod
    def _build_track_token(owner_id: str, audio_id: str, access_hash: Optional[str]) -> str:
        """
        Собирает токен трека формата `<owner>_<audio>_<hash?>`.
        """
        if access_hash:
            return f"{owner_id}_{audio_id}_{access_hash}"
        return f"{owner_id}_{audio_id}"

    @staticmethod
    def _build_playlist_token(owner_id: str, playlist_id: str, access_hash: Optional[str]) -> str:
        """
        Собирает токен плейлиста формата `<owner>_<playlist>_<hash?>`.
        """
        if access_hash:
            return f"{owner_id}_{playlist_id}_{access_hash}"
        return f"{owner_id}_{playlist_id}"

    @staticmethod
    def _build_track_canonical_url(owner_id: str, audio_id: str, access_hash: Optional[str]) -> str:
        """
        Строит канонический URL трека VK Music.
        """
        return f"https://vk.com/audio{VKHandler._build_track_token(owner_id, audio_id, access_hash)}"

    @staticmethod
    def _build_playlist_canonical_url(owner_id: str, playlist_id: str, access_hash: Optional[str]) -> str:
        """
        Строит канонический URL плейлиста VK Music.
        """
        return f"https://vk.com/music/playlist/{VKHandler._build_playlist_token(owner_id, playlist_id, access_hash)}"

    @staticmethod
    def _normalize_vk_url(url: str) -> str:
        """
        Нормализует URL VK (домен + трекинговые query-параметры).
        """
        parts = urlsplit(url)
        netloc = parts.netloc.lower()
        if netloc in {"vk.ru", "m.vk.ru", "vk.com", "m.vk.com"}:
            netloc = "vk.com"
        elif netloc == "www.vk.ru":
            netloc = "www.vk.com"

        query_items = parse_qsl(parts.query, keep_blank_values=True)
        filtered_items = [
            (key, value)
            for key, value in query_items
            if key.lower() not in VKHandler.TRACKING_QUERY_PARAMS
            and not key.lower().startswith("utm_")
        ]
        normalized_query = urlencode(filtered_items, doseq=True)
        normalized_path = parts.path.rstrip("/") or parts.path

        return urlunsplit((parts.scheme or "https", netloc, normalized_path, normalized_query, parts.fragment))

    def _detect_content_type(
        self,
        url: str,
    ) -> Tuple[Optional[str], Optional[re.Match[str]]]:
        """
        Определяет поддерживаемый тип VK Music контента.
        """
        path = urlsplit(url).path.strip("/")
        playlist_match = self.PLAYLIST_PATH_PATTERN.match(path)
        if playlist_match:
            return "playlist", playlist_match

        track_match = self.TRACK_PATH_PATTERN.match(path)
        if track_match:
            return "audio", track_match

        return None, None

    @staticmethod
    def _is_badbrowser_url(url: str) -> bool:
        """
        Проверяет, что URL указывает на interstitial `badbrowser.php`.
        """
        parsed = urlsplit(url)
        return parsed.path.lower().endswith("/badbrowser.php")

    def _warn_badbrowser_redirect(self, requested_url: str, response_url: str) -> None:
        """
        Логирует редирект на `badbrowser.php` один раз для пары URL.
        """
        pair = (requested_url, response_url)
        if pair in self._badbrowser_logged_pairs:
            return
        self._badbrowser_logged_pairs.add(pair)
        logger.warning(
            "VK request redirected to badbrowser.php: requested=%s, redirected=%s. "
            "Likely anti-bot/interstitial response; valid auth cookies may be required.",
            requested_url,
            response_url,
        )

    async def _fetch_html(self, session: aiohttp.ClientSession, url: str) -> Optional[str]:
        """
        Загружает HTML-страницу.
        """
        try:
            async with session.get(
                url,
                allow_redirects=True,
                cookies=self._request_cookies or None,
            ) as response:
                response_url = str(response.url)
                if self._is_badbrowser_url(response_url):
                    self._warn_badbrowser_redirect(url, response_url)
                    return None
                if response.status != 200:
                    logger.warning("VK HTML request failed (%s): %s", response.status, url)
                    return None
                return await response.text(errors="ignore")
        except Exception as exc:
            logger.warning("VK HTML request failed for %s: %s", url, exc)
            return None

    async def _post_json(
        self,
        session: aiohttp.ClientSession,
        url: str,
        form_data: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Выполняет POST и возвращает JSON-ответ VK.
        """
        try:
            async with session.post(
                url,
                data=form_data,
                allow_redirects=True,
                cookies=self._request_cookies or None,
            ) as response:
                response_url = str(response.url)
                if self._is_badbrowser_url(response_url):
                    self._warn_badbrowser_redirect(url, response_url)
                    return None
                if response.status != 200:
                    logger.warning("VK POST request failed (%s): %s", response.status, url)
                    return None
                text = await response.text(errors="ignore")
        except Exception as exc:
            logger.warning("VK POST request failed for %s: %s", url, exc)
            return None

        normalized_text = text.lstrip()
        if normalized_text.startswith("<!--"):
            normalized_text = normalized_text[4:]
        if normalized_text.endswith("-->"):
            normalized_text = normalized_text[:-3]
        normalized_text = normalized_text.strip()
        try:
            payload = json.loads(normalized_text)
        except json.JSONDecodeError as exc:
            logger.warning("VK response is not valid JSON for %s: %s", url, exc)
            return None

        return payload if isinstance(payload, dict) else None

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

    @staticmethod
    def _extract_ld_objects(html_text: str) -> list[Dict[str, Any]]:
        """
        Извлекает JSON-LD объекты из HTML.
        """
        soup = BeautifulSoup(html_text, "html.parser")
        objects: list[Dict[str, Any]] = []
        for node in soup.find_all("script", attrs={"type": "application/ld+json"}):
            raw_payload = node.string or node.get_text(strip=False) or ""
            if not raw_payload.strip():
                continue
            try:
                parsed = json.loads(raw_payload)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                objects.append(parsed)
            elif isinstance(parsed, list):
                objects.extend(item for item in parsed if isinstance(item, dict))
        return objects

    @staticmethod
    def _extract_artist_name(value: Any) -> Optional[str]:
        """
        Извлекает имя артиста из JSON-LD структуры.
        """
        if isinstance(value, str):
            cleaned = value.strip()
            return cleaned if cleaned else None

        if isinstance(value, dict):
            return VKHandler._first_non_empty(
                value.get("name"),
                value.get("title"),
            )

        if isinstance(value, list):
            names = [VKHandler._extract_artist_name(item) for item in value]
            filtered = [name for name in names if isinstance(name, str) and name.strip()]
            if filtered:
                return ", ".join(filtered)
        return None

    @staticmethod
    def _extract_first_http_url(value: Any) -> Optional[str]:
        """
        Возвращает первый HTTP(S) URL из произвольной структуры.
        """
        if isinstance(value, str):
            return value if value.startswith(("http://", "https://")) else None
        if isinstance(value, list):
            for item in value:
                found = VKHandler._extract_first_http_url(item)
                if found:
                    return found
            return None
        if isinstance(value, dict):
            for nested in value.values():
                found = VKHandler._extract_first_http_url(nested)
                if found:
                    return found
        return None

    @staticmethod
    def _parse_iso8601_duration(duration_value: Any) -> Optional[int]:
        """
        Преобразует длительность ISO8601 (`PT3M12S`) в секунды.
        """
        if not isinstance(duration_value, str):
            return None
        match = re.match(r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$", duration_value.strip(), re.IGNORECASE)
        if not match:
            return None
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)
        total = hours * 3600 + minutes * 60 + seconds
        return total if total > 0 else None

    @staticmethod
    def _strip_html(value: Any) -> Optional[str]:
        """
        Возвращает текст без HTML-тегов.
        """
        if not isinstance(value, str):
            return None
        cleaned = value.strip()
        if not cleaned:
            return None
        if "<" not in cleaned:
            return cleaned
        text = BeautifulSoup(cleaned, "html.parser").get_text(" ", strip=True)
        return text or None

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

        def _download() -> Optional[Path]:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(hls_url, download=True)
                if not isinstance(info, dict):
                    return None
                return Path(ydl.prepare_filename(info))

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
        ydl_opts.update(
            self._build_ytdlp_cookiefile_opts(
                provider_key="vk",
                provider_name="VK",
                enabled=VK_COOKIES_ENABLED,
                cookie_path=VK_COOKIES,
                path_env_name="VK_COOKIES_PATH",
            )
        )
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

    @staticmethod
    def _build_track_candidates(owner_id: str, audio_id: str, access_hash: Optional[str]) -> tuple[str, ...]:
        """
        Возвращает VK URL-кандидаты трека для web/mobile extraction.
        """
        token = VKHandler._build_track_token(owner_id, audio_id, access_hash)
        return (f"https://vk.com/audio{token}",)

    @staticmethod
    def _build_playlist_candidates(owner_id: str, playlist_id: str, access_hash: Optional[str]) -> tuple[str, ...]:
        """
        Возвращает VK URL-кандидаты плейлиста для web/mobile extraction.
        """
        token = VKHandler._build_playlist_token(owner_id, playlist_id, access_hash)
        return (f"https://vk.com/music/playlist/{token}",)

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

    @classmethod
    def _extract_playlist_object_from_payload(cls, payload: Any) -> Optional[Dict[str, Any]]:
        """
        Извлекает объект playlist из ответа `load_section`.
        """
        if isinstance(payload, list) and len(payload) > 1 and isinstance(payload[1], list) and payload[1]:
            first_item = payload[1][0]
            if isinstance(first_item, dict) and isinstance(first_item.get("list"), list):
                return first_item

        def _walk(value: Any) -> Iterable[Dict[str, Any]]:
            if isinstance(value, dict):
                if isinstance(value.get("list"), list):
                    yield value
                for nested in value.values():
                    yield from _walk(nested)
                return
            if isinstance(value, list):
                for nested in value:
                    yield from _walk(nested)

        return next(_walk(payload), None)

    async def _fetch_playlist_page_via_load_section(
        self,
        session: aiohttp.ClientSession,
        owner_id: str,
        playlist_id: str,
        access_hash: Optional[str],
        offset: int,
        is_preload: bool,
    ) -> Optional[Dict[str, Any]]:
        """
        Загружает страницу плейлиста через `al_audio.php?act=load_section`.
        """
        response = await self._post_json(
            session,
            "https://vk.com/al_audio.php?act=load_section",
            {
                "al": "1",
                "type": "playlist",
                "owner_id": owner_id,
                "playlist_id": playlist_id,
                "access_hash": access_hash or "",
                "from_id": "",
                "offset": str(offset),
                "is_loading_all": "1",
                "is_preload": "1" if is_preload else "0",
                "context": self.VK_PLAYLIST_CONTEXT,
            },
        )
        if not response:
            return None

        return self._extract_playlist_object_from_payload(response.get("payload"))

    async def _load_playlist_via_api(
        self,
        session: aiohttp.ClientSession,
        owner_id: str,
        playlist_id: str,
        access_hash: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        """
        Загружает плейлист через API-цепочку `load_section` c поддержкой пагинации.
        """
        playlist_meta: Optional[Dict[str, Any]] = None
        tracks: list[list[Any]] = []
        seen_track_ids: set[Tuple[int, int]] = set()

        offset = 0
        for page_index in range(self.VK_MAX_PLAYLIST_PAGES):
            page_data = await self._fetch_playlist_page_via_load_section(
                session=session,
                owner_id=owner_id,
                playlist_id=playlist_id,
                access_hash=access_hash,
                offset=offset,
                is_preload=page_index == 0,
            )
            if not page_data:
                break

            if playlist_meta is None:
                playlist_meta = dict(page_data)

            raw_tracks = page_data.get("list")
            if isinstance(raw_tracks, list):
                for raw_track in raw_tracks:
                    if not self._looks_like_audio_tuple(raw_track):
                        continue
                    tuple_owner = self._safe_int(raw_track[self.AUDIO_INDEX_OWNER_ID])
                    tuple_audio = self._safe_int(raw_track[self.AUDIO_INDEX_ID])
                    if tuple_owner is None or tuple_audio is None:
                        continue
                    track_key = (tuple_owner, tuple_audio)
                    if track_key in seen_track_ids:
                        continue
                    seen_track_ids.add(track_key)
                    tracks.append(raw_track)

            has_more = bool(page_data.get("hasMore"))
            next_offset = self._safe_int(page_data.get("nextOffset"))
            if not has_more or next_offset is None or next_offset <= offset:
                break
            offset = next_offset

        if playlist_meta is None:
            return None

        playlist_meta["list"] = tracks
        if self._safe_int(playlist_meta.get("totalCount")) is None:
            playlist_meta["totalCount"] = len(tracks)
        return playlist_meta

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

    @staticmethod
    def _iter_playlist_track_nodes(value: Any) -> Iterable[Dict[str, Any]]:
        """
        Итерирует track-объекты из JSON-LD playlist структуры.
        """
        if isinstance(value, dict):
            if "item" in value:
                yield from VKHandler._iter_playlist_track_nodes(value.get("item"))
                return
            if "track" in value and isinstance(value.get("track"), (dict, list)):
                yield from VKHandler._iter_playlist_track_nodes(value.get("track"))
                return
            yield value
            return

        if isinstance(value, list):
            for item in value:
                yield from VKHandler._iter_playlist_track_nodes(item)

    def _extract_playlist_metadata(self, html_text: str, canonical_url: str) -> Dict[str, Any]:
        """
        Извлекает метаданные плейлиста и список треков без скачивания.
        """
        soup = BeautifulSoup(html_text, "html.parser")

        playlist_title = "VK Music Playlist"
        owner = "Unknown"
        tracks: list[Dict[str, Any]] = []
        seen_track_urls: set[str] = set()
        track_count: Optional[int] = None

        for payload in self._extract_ld_objects(html_text):
            payload_type = payload.get("@type")
            payload_types: set[str] = set()
            if isinstance(payload_type, str):
                payload_types.add(payload_type.lower())
            elif isinstance(payload_type, list):
                payload_types.update(
                    item.lower()
                    for item in payload_type
                    if isinstance(item, str)
                )

            if "musicplaylist" not in payload_types and "itemlist" not in payload_types:
                continue

            playlist_title = self._first_non_empty(
                payload.get("name"),
                payload.get("headline"),
                playlist_title,
            ) or playlist_title
            owner = self._first_non_empty(
                self._extract_artist_name(payload.get("byArtist")),
                self._extract_artist_name(payload.get("author")),
                owner,
            ) or owner

            raw_track_count = payload.get("numTracks") or payload.get("numberOfItems")
            track_count = self._safe_int(raw_track_count) or track_count

            for track_node in self._iter_playlist_track_nodes(
                payload.get("track") or payload.get("itemListElement") or []
            ):
                track_title = self._first_non_empty(
                    track_node.get("name"),
                    track_node.get("title"),
                    track_node.get("headline"),
                )
                track_performer = self._first_non_empty(
                    self._extract_artist_name(track_node.get("byArtist")),
                    self._extract_artist_name(track_node.get("author")),
                    "Unknown",
                ) or "Unknown"
                track_duration = (
                    self._parse_iso8601_duration(track_node.get("duration"))
                    or self._safe_int(track_node.get("duration"))
                )
                track_source_url = self._first_non_empty(
                    self._extract_first_http_url(track_node.get("url")),
                    self._extract_first_http_url(track_node.get("sameAs")),
                )
                track_cover_url = self._first_non_empty(
                    self._extract_first_http_url(track_node.get("image")),
                    self._extract_first_http_url(track_node.get("thumbnailUrl")),
                )

                if isinstance(track_source_url, str):
                    normalized_source_url = self._normalize_vk_url(track_source_url)
                else:
                    normalized_source_url = None

                dedupe_key = normalized_source_url or f"{track_performer}:{track_title}:{track_duration}"
                if dedupe_key in seen_track_urls:
                    continue
                seen_track_urls.add(dedupe_key)

                tracks.append(
                    {
                        "title": track_title or "VK Track",
                        "performer": track_performer,
                        "duration": track_duration,
                        "source_url": normalized_source_url,
                        "canonical_url": normalized_source_url,
                        "cover_url": track_cover_url,
                    }
                )

        if not tracks:
            for match in self.TRACK_LINK_PATTERN.finditer(html_text):
                owner_id = match.group("owner")
                audio_id = match.group("audio")
                access_hash = match.group("access_hash")
                track_url = self._build_track_canonical_url(owner_id, audio_id, access_hash)
                if track_url in seen_track_urls:
                    continue
                seen_track_urls.add(track_url)
                tracks.append(
                    {
                        "title": "VK Track",
                        "performer": "Unknown",
                        "duration": None,
                        "source_url": track_url,
                        "canonical_url": track_url,
                        "cover_url": None,
                    }
                )

        og_title_node = soup.find("meta", attrs={"property": "og:title"})
        og_title = og_title_node.get("content", "") if og_title_node else ""
        if isinstance(og_title, str) and og_title.strip():
            playlist_title = self._first_non_empty(
                og_title.replace("| VK", "").strip(),
                playlist_title,
            ) or playlist_title

        og_description_node = soup.find("meta", attrs={"property": "og:description"})
        og_description = og_description_node.get("content", "") if og_description_node else ""
        if isinstance(og_description, str) and og_description.strip():
            owner_match = re.search(r"от\s+([^.,]+)", og_description, re.IGNORECASE)
            if owner_match:
                owner = self._first_non_empty(owner_match.group(1), owner) or owner

        if track_count is None:
            for pattern in self.TRACK_COUNT_PATTERNS:
                match = pattern.search(html_text)
                if not match:
                    continue
                track_count = self._safe_int(match.group(1))
                if track_count is not None:
                    break

        if track_count is None:
            track_count = len(tracks)

        return {
            "playlist_title": playlist_title,
            "owner": owner,
            "track_count": track_count,
            "tracks": tracks,
            "canonical_url": canonical_url,
        }

    @staticmethod
    def _build_playlist_caption(
        playlist_title: str,
        owner: str,
        track_count: int,
        tracks: Sequence[Dict[str, Any]],
    ) -> str:
        """
        Формирует текст превью плейлиста для Telegram.
        """
        lines = [
            f"🎵 {playlist_title}",
            f"👤 {owner}",
            f"🎼 Треков: {track_count}",
        ]

        if tracks:
            lines.append("")
            lines.append("Первые треки:")
            for index, track in enumerate(tracks[:5], start=1):
                title = str(track.get("title") or "VK Track")
                performer = str(track.get("performer") or "Unknown")
                lines.append(f"{index}. {performer} — {title}")

        return "\n".join(lines)

    async def _process_vk_playlist(
        self,
        session: aiohttp.ClientSession,
        original_url: str,
        context: str,
        owner_id: str,
        playlist_id: str,
        access_hash: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        """
        Обрабатывает плейлист VK Music (без пакетной загрузки файлов).
        """
        canonical_url = self._build_playlist_canonical_url(owner_id, playlist_id, access_hash)
        api_playlist = await self._load_playlist_via_api(
            session=session,
            owner_id=owner_id,
            playlist_id=playlist_id,
            access_hash=access_hash,
        )

        if api_playlist:
            raw_tracks = api_playlist.get("list")
            playlist_tracks = [
                self._audio_tuple_to_track_preview(track_tuple)
                for track_tuple in raw_tracks
                if self._looks_like_audio_tuple(track_tuple)
            ] if isinstance(raw_tracks, list) else []

            playlist_title = self._first_non_empty(
                self._strip_html(api_playlist.get("title")),
                self._strip_html(api_playlist.get("subTitle")),
                "VK Music Playlist",
            ) or "VK Music Playlist"
            playlist_owner = self._first_non_empty(
                self._strip_html(api_playlist.get("authorName")),
                self._strip_html(api_playlist.get("authorLine")),
                "Unknown",
            ) or "Unknown"
            track_count = self._safe_int(api_playlist.get("totalCount")) or len(playlist_tracks)

            if playlist_tracks:
                caption_text = self._build_playlist_caption(
                    playlist_title=playlist_title,
                    owner=playlist_owner,
                    track_count=track_count,
                    tracks=playlist_tracks,
                )
                return {
                    "type": "playlist",
                    "source_name": self.source_name,
                    "title": playlist_title,
                    "uploader": playlist_owner,
                    "source_url": original_url,
                    "canonical_url": canonical_url,
                    "original_url": original_url,
                    "context": context,
                    "caption_text": caption_text,
                    "metadata": {
                        "playlist_title": playlist_title,
                        "owner": playlist_owner,
                        "track_count": track_count,
                        "tracks": playlist_tracks,
                        "canonical_url": canonical_url,
                    },
                    "tracks": playlist_tracks,
                }

            logger.warning("VK playlist API returned no tracks, fallback to HTML parsing: %s", canonical_url)

        candidate_urls = self._build_playlist_candidates(owner_id, playlist_id, access_hash)
        best_metadata: Optional[Dict[str, Any]] = None
        for candidate_url in candidate_urls:
            html_text = await self._fetch_html(session, candidate_url)
            if not html_text:
                continue
            extracted_metadata = self._extract_playlist_metadata(html_text, canonical_url=canonical_url)
            if not best_metadata:
                best_metadata = extracted_metadata
                continue
            old_tracks = best_metadata.get("tracks", [])
            new_tracks = extracted_metadata.get("tracks", [])
            if isinstance(old_tracks, list) and isinstance(new_tracks, list) and len(new_tracks) > len(old_tracks):
                best_metadata = extracted_metadata

        if not best_metadata:
            logger.error("VK playlist page is unavailable: %s", canonical_url)
            return None

        tracks = best_metadata.get("tracks", [])
        if not isinstance(tracks, list) or not tracks:
            logger.error("VK playlist parsed without tracks: %s", canonical_url)
            return None

        playlist_title = str(best_metadata.get("playlist_title") or "VK Music Playlist")
        playlist_owner = str(best_metadata.get("owner") or "Unknown")
        track_count = self._safe_int(best_metadata.get("track_count")) or len(tracks)
        caption_text = self._build_playlist_caption(
            playlist_title=playlist_title,
            owner=playlist_owner,
            track_count=track_count,
            tracks=tracks,
        )

        return {
            "type": "playlist",
            "source_name": self.source_name,
            "title": playlist_title,
            "uploader": playlist_owner,
            "source_url": original_url,
            "canonical_url": canonical_url,
            "original_url": original_url,
            "context": context,
            "caption_text": caption_text,
            "metadata": {
                "playlist_title": playlist_title,
                "owner": playlist_owner,
                "track_count": track_count,
                "tracks": tracks,
                "canonical_url": canonical_url,
            },
            "tracks": tracks,
        }

    async def process(
        self,
        url: str,
        context: str,
        resolved_url: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Основной вход обработчика VK.
        """
        target_url = self._normalize_vk_url(resolved_url or url)
        content_type, content_match = self._detect_content_type(target_url)
        if not content_type or not content_match:
            logger.warning("Unsupported VK URL type: %s", target_url)
            return None

        timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_read=30)
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "ru,en-US;q=0.9,en;q=0.8",
            "Referer": "https://vk.com/",
            "Origin": "https://vk.com",
            "X-Requested-With": "XMLHttpRequest",
        }

        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            if content_type == "audio":
                return await self._process_vk_audio(
                    session=session,
                    original_url=url,
                    context=context,
                    owner_id=content_match.group("owner"),
                    audio_id=content_match.group("audio"),
                    access_hash=content_match.group("access_hash"),
                )

            if content_type == "playlist":
                return await self._process_vk_playlist(
                    session=session,
                    original_url=url,
                    context=context,
                    owner_id=content_match.group("owner"),
                    playlist_id=content_match.group("playlist"),
                    access_hash=content_match.group("access_hash"),
                )

        logger.warning("VK content type is not supported by process() branch: %s", content_type)
        return None

