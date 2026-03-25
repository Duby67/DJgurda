"""
Явные зависимости VK-контура.

Модуль убирает скрытую зависимость от MRO и предоставляет
компоненты, которые передаются в процессоры как explicit dependencies.
"""

from __future__ import annotations

import html
import json
import logging
import re
from pathlib import Path
from typing import Any, Optional, Protocol
from urllib.parse import unquote, urlsplit

import aiohttp
from bs4 import BeautifulSoup

from src.config import VK_COOKIES, VK_COOKIES_ENABLED
from src.handlers.infrastructure import (
    DelayPolicyService,
    HttpFileService,
    RuntimePathService,
    YtdlpMediaGroupService,
    YtdlpOptionBuilder,
)
from src.utils.cookies import CookieFile

logger = logging.getLogger(__name__)


class VKRequestContextProtocol(Protocol):
    """Контракт shared VK-хелперов и сетевых операций."""

    _request_cookies: dict[str, str]
    _cookie_buckets: dict[str, dict[str, str]]
    _vk_user_id: int
    VK_AUDIO_B64_ALPHABET: str
    VK_OP_SEPARATOR: str
    VK_ARG_SEPARATOR: str

    def _build_vk_cookie_opts(self) -> dict[str, str]:
        """Возвращает cookiefile-опции для yt-dlp fallback."""

    def build_browser_headers(self, *, referer: Optional[str] = None) -> dict[str, str]:
        """Возвращает browser-like headers для VK HTTP и yt-dlp запросов."""

    async def _fetch_html(self, session: aiohttp.ClientSession, url: str) -> Optional[str]:
        """Загружает HTML-страницу."""

    async def _post_json(
        self,
        session: aiohttp.ClientSession,
        url: str,
        form_data: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        """Выполняет POST и возвращает JSON-ответ VK."""


class VKMediaGatewayProtocol(Protocol):
    """Контракт low-level операций VK-процессоров."""

    temp_dir: Path
    audio_limit: int
    photo_limit: int

    def _generate_unique_path(self, identifier: str, suffix: str = "") -> Path:
        """Генерирует уникальный runtime-путь."""

    def _build_ytdlp_opts(
        self,
        default_opts: dict[str, Any],
        ydl_opts: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Объединяет опции yt-dlp."""

    async def _download_thumbnail(
        self,
        url: str,
        dest_path: Path,
        size_limit: Optional[int] = None,
    ) -> bool:
        """Скачивает thumbnail."""

    async def _download_media_group(
        self,
        url: str,
        ydl_opts: dict[str, Any],
        *,
        group_id: Optional[str] = None,
        size_limit: Optional[int] = None,
    ) -> Optional[list[dict[str, Any]]]:
        """Скачивает media-group через yt-dlp."""


class VKRequestContext:
    """Shared-контекст VK: cookies, helper-функции и сетевые вызовы."""

    VK_AUDIO_B64_ALPHABET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMN0PQRSTUVWXYZO123456789+/="
    VK_OP_SEPARATOR = chr(9)
    VK_ARG_SEPARATOR = chr(11)
    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    DEFAULT_ACCEPT_LANGUAGE = "ru,en-US;q=0.9,en;q=0.8"
    DEFAULT_ACCEPT = (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    )
    _VK_STID_UID_PATTERN = re.compile(r"^(?P<user_id>\d+)_")

    def __init__(self, runtime_dir: Path) -> None:
        self._vk_cookies = CookieFile(
            provider_key="vk",
            provider_name="VK",
            enabled=VK_COOKIES_ENABLED,
            cookie_path=VK_COOKIES,
            path_env_name="VK_COOKIES_PATH",
            runtime_dir=runtime_dir,
            log=logger,
        )
        valid_cookie_path = self._vk_cookies.resolve_valid_path()
        self._cookie_buckets = self._load_domain_cookie_buckets(valid_cookie_path)
        self._request_cookies = self._build_default_request_cookies()
        self._vk_user_id = self._extract_vk_user_id_from_cookies(
            self._cookie_buckets.get("vk.com") or self._request_cookies
        )
        self._badbrowser_logged_pairs: set[tuple[str, str]] = set()

    @staticmethod
    def _normalize_cookie_domain(domain: str) -> str:
        """Нормализует домен cookie до host-like вида без ведущей точки."""
        return domain.strip().lstrip(".").lower()

    @classmethod
    def _load_domain_cookie_buckets(cls, cookie_path: Optional[Path]) -> dict[str, dict[str, str]]:
        """Загружает cookies с разделением по доменам из Netscape-файла."""
        if not isinstance(cookie_path, Path) or not cookie_path.exists():
            return {}

        buckets: dict[str, dict[str, str]] = {}
        for raw_line in cookie_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("#HttpOnly_"):
                line = line[len("#HttpOnly_"):]
            elif line.startswith("#"):
                continue

            parts = line.split("\t")
            if len(parts) < 7:
                continue

            domain = cls._normalize_cookie_domain(parts[0])
            name = parts[5].strip()
            value = parts[6].strip()
            if not domain or not name:
                continue

            bucket = buckets.setdefault(domain, {})
            bucket[name] = value

        return buckets

    def _build_default_request_cookies(self) -> dict[str, str]:
        """Строит дефолтный набор cookies с приоритетом `vk.com`."""
        if self._cookie_buckets.get("vk.com"):
            return dict(self._cookie_buckets["vk.com"])

        merged: dict[str, str] = {}
        for bucket in self._cookie_buckets.values():
            merged.update(bucket)
        return merged

    def _cookies_for_url(self, url: str) -> dict[str, str]:
        """Возвращает host-specific cookies для конкретного URL."""
        host = (urlsplit(url).hostname or "").strip().lower()
        if not host:
            return self._request_cookies

        normalized_host = self._normalize_cookie_domain(host)
        if normalized_host in self._cookie_buckets:
            return self._cookie_buckets[normalized_host]

        if normalized_host.endswith(".vk.com") and self._cookie_buckets.get("vk.com"):
            return self._cookie_buckets["vk.com"]

        if normalized_host.endswith(".vkvideo.ru") and self._cookie_buckets.get("vkvideo.ru"):
            return self._cookie_buckets["vkvideo.ru"]

        return self._request_cookies

    @classmethod
    def _extract_vk_user_id_from_cookies(cls, cookies: dict[str, str]) -> int:
        """
        Возвращает user_id для VK audio decode.

        Основной путь — `remixuserid`.
        Fallback — префикс `<uid>_...` в `remixstid`, который часто есть
        в актуальных экспортируемых cookie-файлах даже без `remixuserid`.
        """
        if not isinstance(cookies, dict):
            return 0

        direct_uid = cls._safe_int(cookies.get("remixuserid"))
        if isinstance(direct_uid, int) and direct_uid > 0:
            return direct_uid

        remixstid = cookies.get("remixstid")
        if isinstance(remixstid, str):
            match = cls._VK_STID_UID_PATTERN.match(remixstid.strip())
            if match:
                stid_uid = cls._safe_int(match.group("user_id"))
                if isinstance(stid_uid, int) and stid_uid > 0:
                    return stid_uid

        return 0

    def _build_vk_cookie_opts(self) -> dict[str, str]:
        """Возвращает cookiefile-опции для yt-dlp в VK fallback-сценариях."""
        return self._vk_cookies.build_ytdlp_opts()

    def build_browser_headers(self, *, referer: Optional[str] = None) -> dict[str, str]:
        """Возвращает browser-like headers для VK network paths."""
        effective_referer = referer or "https://vk.com/"
        return {
            "User-Agent": self.DEFAULT_USER_AGENT,
            "Accept": self.DEFAULT_ACCEPT,
            "Accept-Language": self.DEFAULT_ACCEPT_LANGUAGE,
            "Referer": effective_referer,
            "Origin": "https://vk.com",
            "X-Requested-With": "XMLHttpRequest",
        }

    @staticmethod
    def _first_non_empty(*values: Any) -> Optional[str]:
        """Возвращает первую непустую строку."""
        for value in values:
            if isinstance(value, str):
                cleaned = value.strip()
                if cleaned:
                    return cleaned
        return None

    @staticmethod
    def _safe_int(value: Any) -> Optional[int]:
        """Безопасно преобразует значение в int."""
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
        """Приводит escaped-URL из HTML/JSON к обычному виду."""
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
        """Собирает токен трека формата `<owner>_<audio>_<hash?>`."""
        if access_hash:
            return f"{owner_id}_{audio_id}_{access_hash}"
        return f"{owner_id}_{audio_id}"

    @staticmethod
    def _build_playlist_token(owner_id: str, playlist_id: str, access_hash: Optional[str]) -> str:
        """Собирает токен плейлиста формата `<owner>_<playlist>_<hash?>`."""
        if access_hash:
            return f"{owner_id}_{playlist_id}_{access_hash}"
        return f"{owner_id}_{playlist_id}"

    @staticmethod
    def _build_track_canonical_url(owner_id: str, audio_id: str, access_hash: Optional[str]) -> str:
        """Строит канонический URL трека VK Music."""
        token = VKRequestContext._build_track_token(owner_id, audio_id, access_hash)
        return f"https://vk.com/audio{token}"

    @staticmethod
    def _build_playlist_canonical_url(owner_id: str, playlist_id: str, access_hash: Optional[str]) -> str:
        """Строит канонический URL плейлиста VK Music."""
        token = VKRequestContext._build_playlist_token(owner_id, playlist_id, access_hash)
        return f"https://vk.com/music/playlist/{token}"

    @staticmethod
    def _normalize_vk_url(url: str) -> str:
        """Нормализует VK URL для metadata/playlist ссылок."""
        parts = urlsplit(url)
        netloc = parts.netloc.lower()
        if netloc in {"vk.ru", "m.vk.ru", "vk.com", "m.vk.com"}:
            netloc = "vk.com"
        elif netloc == "www.vk.ru":
            netloc = "www.vk.com"
        return f"{parts.scheme or 'https'}://{netloc}{parts.path}"

    @staticmethod
    def _is_badbrowser_url(url: str) -> bool:
        """Проверяет, что URL указывает на interstitial `badbrowser.php`."""
        parsed = urlsplit(url)
        return parsed.path.lower().endswith("/badbrowser.php")

    def _warn_badbrowser_redirect(self, requested_url: str, response_url: str) -> None:
        """Логирует редирект на `badbrowser.php` один раз для пары URL."""
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

    @staticmethod
    def _decode_html_response(raw_bytes: bytes, response: aiohttp.ClientResponse) -> str:
        """Декодирует HTML с уважением к charset из VK-ответа."""
        encoding_candidates: list[str] = []

        response_charset = getattr(response, "charset", None)
        if isinstance(response_charset, str) and response_charset.strip():
            encoding_candidates.append(response_charset.strip())

        try:
            detected_encoding = response.get_encoding()
        except Exception:
            detected_encoding = None
        if isinstance(detected_encoding, str) and detected_encoding.strip():
            encoding_candidates.append(detected_encoding.strip())

        encoding_candidates.extend(["windows-1251", "cp1251", "utf-8"])

        seen: set[str] = set()
        for encoding in encoding_candidates:
            normalized = encoding.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            try:
                return raw_bytes.decode(encoding, errors="ignore")
            except LookupError:
                continue

        return raw_bytes.decode("utf-8", errors="ignore")

    async def _fetch_html(self, session: aiohttp.ClientSession, url: str) -> Optional[str]:
        """Загружает HTML-страницу."""
        try:
            async with session.get(
                url,
                allow_redirects=True,
                cookies=self._cookies_for_url(url) or None,
            ) as response:
                response_url = str(response.url)
                if self._is_badbrowser_url(response_url):
                    self._warn_badbrowser_redirect(url, response_url)
                    return None
                if response.status != 200:
                    logger.warning("VK HTML request failed (%s): %s", response.status, url)
                    return None
                raw_bytes = await response.read()
                return self._decode_html_response(raw_bytes, response)
        except Exception as exc:
            logger.warning("VK HTML request failed for %s: %s", url, exc)
            return None

    async def _post_json(
        self,
        session: aiohttp.ClientSession,
        url: str,
        form_data: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        """Выполняет POST и возвращает JSON-ответ VK."""
        try:
            async with session.post(
                url,
                data=form_data,
                allow_redirects=True,
                cookies=self._cookies_for_url(url) or None,
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
    def _extract_ld_objects(html_text: str) -> list[dict[str, Any]]:
        """Извлекает JSON-LD объекты из HTML."""
        soup = BeautifulSoup(html_text, "html.parser")
        objects: list[dict[str, Any]] = []
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
        """Извлекает имя артиста из JSON-LD структуры."""
        if isinstance(value, str):
            cleaned = value.strip()
            return cleaned if cleaned else None

        if isinstance(value, dict):
            return VKRequestContext._first_non_empty(
                value.get("name"),
                value.get("title"),
            )

        if isinstance(value, list):
            names = [VKRequestContext._extract_artist_name(item) for item in value]
            filtered = [name for name in names if isinstance(name, str) and name.strip()]
            if filtered:
                return ", ".join(filtered)
        return None

    @staticmethod
    def _extract_first_http_url(value: Any) -> Optional[str]:
        """Возвращает первый HTTP(S) URL из произвольной структуры."""
        if isinstance(value, str):
            return value if value.startswith(("http://", "https://")) else None
        if isinstance(value, list):
            for item in value:
                found = VKRequestContext._extract_first_http_url(item)
                if found:
                    return found
            return None
        if isinstance(value, dict):
            for nested in value.values():
                found = VKRequestContext._extract_first_http_url(nested)
                if found:
                    return found
        return None

    @staticmethod
    def _parse_iso8601_duration(duration_value: Any) -> Optional[int]:
        """Преобразует длительность ISO8601 (`PT3M12S`) в секунды."""
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
        """Возвращает текст без HTML-тегов."""
        if not isinstance(value, str):
            return None
        cleaned = value.strip()
        if not cleaned:
            return None
        if "<" not in cleaned:
            return cleaned
        text = BeautifulSoup(cleaned, "html.parser").get_text(" ", strip=True)
        return text or None


class VKMediaGateway:
    """
    Реализация low-level операций VK через composition-сервисы.

    Сохраняет минимальный API, который ожидают VK-процессоры.
    """

    def __init__(self, runtime_dir: Path) -> None:
        self.temp_dir = runtime_dir
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self._runtime_paths = RuntimePathService(runtime_dir=runtime_dir)
        self._delay_policy = DelayPolicyService()
        self._http_service = HttpFileService(delay_policy=self._delay_policy)
        self._option_builder = YtdlpOptionBuilder(scope=self.__class__.__name__)
        self._media_group_service = YtdlpMediaGroupService(
            runtime_paths=self._runtime_paths,
            delay_policy=self._delay_policy,
            option_builder=self._option_builder,
        )
        self.audio_limit = self._http_service.audio_limit
        self.photo_limit = self._http_service.photo_limit

    def _generate_unique_path(self, identifier: str, suffix: str = "") -> Path:
        """Генерирует уникальный runtime-путь."""
        return self._runtime_paths.generate_unique_path(identifier, suffix=suffix)

    def _build_ytdlp_opts(
        self,
        default_opts: dict[str, Any],
        ydl_opts: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Объединяет опции yt-dlp и добавляет тихий logger."""
        return self._option_builder.build(default_opts, ydl_opts)

    async def _download_thumbnail(
        self,
        url: str,
        dest_path: Path,
        size_limit: Optional[int] = None,
    ) -> bool:
        """Скачивает thumbnail с проверкой лимита размера."""
        return await self._http_service.download_thumbnail(url, dest_path, size_limit=size_limit)

    async def _download_media_group(
        self,
        url: str,
        ydl_opts: dict[str, Any],
        *,
        group_id: Optional[str] = None,
        size_limit: Optional[int] = None,
    ) -> Optional[list[dict[str, Any]]]:
        """Скачивает media-group через yt-dlp с текущими runtime/policy сервисами."""
        return await self._media_group_service.download_media_group(
            url,
            ydl_opts,
            group_id=group_id,
            size_limit=size_limit,
        )
