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
    YtdlpOptionBuilder,
)
from src.utils.cookies import CookieFile

logger = logging.getLogger(__name__)


class VKRequestContextProtocol(Protocol):
    """Контракт shared VK-хелперов и сетевых операций."""

    _request_cookies: dict[str, str]
    _vk_user_id: int
    VK_AUDIO_B64_ALPHABET: str
    VK_OP_SEPARATOR: str
    VK_ARG_SEPARATOR: str

    def _build_vk_cookie_opts(self) -> dict[str, str]:
        """Возвращает cookiefile-опции для yt-dlp fallback."""

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


class VKRequestContext:
    """Shared-контекст VK: cookies, helper-функции и сетевые вызовы."""

    VK_AUDIO_B64_ALPHABET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMN0PQRSTUVWXYZO123456789+/="
    VK_OP_SEPARATOR = chr(9)
    VK_ARG_SEPARATOR = chr(11)

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
        self._request_cookies = self._vk_cookies.build_request_cookies()
        self._vk_user_id = self._safe_int(self._request_cookies.get("remixuserid")) or 0
        self._badbrowser_logged_pairs: set[tuple[str, str]] = set()

    def _build_vk_cookie_opts(self) -> dict[str, str]:
        """Возвращает cookiefile-опции для yt-dlp в VK fallback-сценариях."""
        return self._vk_cookies.build_ytdlp_opts()

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

    async def _fetch_html(self, session: aiohttp.ClientSession, url: str) -> Optional[str]:
        """Загружает HTML-страницу."""
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
        form_data: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        """Выполняет POST и возвращает JSON-ответ VK."""
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
