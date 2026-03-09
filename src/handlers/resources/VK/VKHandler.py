"""
Главный обработчик VK Music (audio + playlist).
"""

from __future__ import annotations

import html
import json
import logging
import re
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

import aiohttp
from bs4 import BeautifulSoup

from src.config import VK_COOKIES, VK_COOKIES_ENABLED
from src.handlers.base import BaseHandler
from src.utils.cookies import CookieFile
from .VKAudio import VKAudio
from .VKPlaylist import VKPlaylist

logger = logging.getLogger(__name__)


class VKHandler(BaseHandler, VKAudio, VKPlaylist):
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
        self._vk_cookies = CookieFile(
            provider_key="vk",
            provider_name="VK",
            enabled=VK_COOKIES_ENABLED,
            cookie_path=VK_COOKIES,
            path_env_name="VK_COOKIES_PATH",
            runtime_dir=self.temp_dir,
            log=logger,
        )
        self._request_cookies = self._vk_cookies.build_request_cookies()
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

    def _build_vk_cookie_opts(self) -> Dict[str, str]:
        """
        Возвращает cookiefile-опции для yt-dlp в VK fallback-сценариях.
        """
        return self._vk_cookies.build_ytdlp_opts()

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
