"""
Процессор VK profile/community card.
"""

from __future__ import annotations

import html
import json
import logging
import re
from typing import Any, Optional

import aiohttp
from bs4 import BeautifulSoup

from src.handlers.contracts import ContentType, MediaResult
from .VKDependencies import VKMediaGatewayProtocol, VKRequestContextProtocol

logger = logging.getLogger(__name__)


class VKProfile:
    """Процессор profile/community страницы VK."""

    INFO_SELECTORS = (
        ".page_info_wrap .labeled",
        ".page_info_wrap .line_cell",
        ".group_info_row",
        ".profile_info_row",
    )
    SPLIT_PATTERN = re.compile(r"\s*(?:[|;•·]+)\s*")
    MAX_INFO_LINES = 7
    MAX_INFO_TOTAL = 900
    ACCOUNT_ID_PATTERN = re.compile(r"^(?:id)?(?P<user_id>\d+)$", re.IGNORECASE)
    EMBEDDED_ESCAPED_FRAGMENT_PATTERN = r'[^"\\]*(?:\\.[^"\\]*)*'
    EMBEDDED_ESCAPED_STRING_PATTERN = r'(?P<value>[^"\\]*(?:\\.[^"\\]*)*)'
    GENERIC_EMBEDDED_TITLES = frozenset({"wall", "photos", "videos", "articles", "short_videos"})

    def __init__(
        self,
        *,
        request_context: VKRequestContextProtocol,
        media_gateway: VKMediaGatewayProtocol,
    ) -> None:
        self._request_context = request_context
        self._media_gateway = media_gateway

    def __getattr__(self, name: str) -> Any:
        if hasattr(self._request_context, name):
            return getattr(self._request_context, name)
        if hasattr(self._media_gateway, name):
            return getattr(self._media_gateway, name)
        raise AttributeError(name)

    @staticmethod
    def _strip_vk_suffix(value: str) -> str:
        """Убирает стандартные суффиксы VK из display title."""
        cleaned = value.strip()
        for suffix in ("| ВКонтакте", "— ВКонтакте", "- ВКонтакте"):
            if cleaned.endswith(suffix):
                cleaned = cleaned[: -len(suffix)].rstrip()
        return cleaned or value.strip()

    @staticmethod
    def _normalize_info_line(value: Optional[str]) -> Optional[str]:
        """Чистит и нормализует одну строку публичной информации."""
        if not isinstance(value, str):
            return None
        stripped = value.strip()
        if not stripped:
            return None
        text = BeautifulSoup(stripped, "html.parser").get_text(" ", strip=True)
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            return None
        if len(text) > 220:
            text = text[:217].rstrip() + "..."
        return text

    @staticmethod
    def _decode_embedded_json_string(value: str) -> Optional[str]:
        """Декодирует JSON-escaped строку из embedded VK payload."""
        if not isinstance(value, str) or not value:
            return None
        try:
            return json.loads(f'"{value}"')
        except json.JSONDecodeError:
            return html.unescape(value.replace("\\n", "\n").replace("\\/", "/"))

    def _extract_ld_identity(self, html_text: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """Возвращает display-name, avatar и canonical URL из JSON-LD, если они есть."""
        for payload in self._extract_ld_objects(html_text):
            candidate = payload
            main_entity = payload.get("mainEntity")
            if isinstance(main_entity, dict):
                candidate = main_entity

            display_name = self._first_non_empty(
                self._strip_html(candidate.get("name")),
                self._strip_html(candidate.get("alternateName")),
            )
            avatar_url = self._extract_first_http_url(candidate.get("image")) or self._extract_first_http_url(
                payload.get("image")
            )
            canonical_url = self._extract_first_http_url(candidate.get("url")) or self._extract_first_http_url(
                payload.get("url")
            )

            if display_name or avatar_url or canonical_url:
                return display_name, avatar_url, canonical_url

        return None, None, None

    def _extract_public_info(self, soup: BeautifulSoup, html_text: str) -> tuple[str, ...]:
        """Извлекает публичные data points для user/community card."""
        candidates: list[str] = []

        for payload in self._extract_ld_objects(html_text):
            for key in ("description", "alternateName", "jobTitle", "headline"):
                value = payload.get(key)
                if isinstance(value, str):
                    candidates.append(value)

        for attrs in (
            {"property": "og:description"},
            {"name": "description"},
        ):
            node = soup.find("meta", attrs=attrs)
            if node:
                content = node.get("content")
                if isinstance(content, str):
                    candidates.append(content)

        for selector in self.INFO_SELECTORS:
            for node in soup.select(selector):
                candidates.append(node.get_text(" ", strip=True))

        lines: list[str] = []
        seen: set[str] = set()
        total_len = 0
        for raw_value in candidates:
            fragments = [raw_value]
            if self.SPLIT_PATTERN.search(raw_value):
                fragments = [part for part in self.SPLIT_PATTERN.split(raw_value) if part]

            for fragment in fragments:
                normalized = self._normalize_info_line(fragment)
                if not normalized:
                    continue
                lowered = normalized.lower()
                if lowered in seen:
                    continue
                seen.add(lowered)
                projected = total_len + len(normalized)
                if projected > self.MAX_INFO_TOTAL and lines:
                    return tuple(lines)
                lines.append(normalized)
                total_len = projected
                if len(lines) >= self.MAX_INFO_LINES:
                    return tuple(lines)
        return tuple(lines)

    def _match_embedded_field(self, html_text: str, pattern: str) -> Optional[str]:
        """Возвращает декодированное значение первого regex match из embedded VK payload."""
        match = re.search(pattern, html_text, re.DOTALL)
        if not match:
            return None
        return self._decode_embedded_json_string(match.group("value"))

    def _extract_embedded_account_identity(
        self,
        html_text: str,
        screen_name: str,
    ) -> tuple[Optional[str], Optional[str], Optional[str], tuple[str, ...]]:
        """Извлекает user identity из embedded users.get response."""
        match = self.ACCOUNT_ID_PATTERN.match(screen_name.strip())
        if not match:
            return None, None, None, ()

        user_id = match.group("user_id")
        base_pattern = rf'"response":\[\{{"id":{user_id}.{{0,9000}}?'

        first_name = self._match_embedded_field(
            html_text,
            base_pattern + rf'"first_name_nom":"{self.EMBEDDED_ESCAPED_STRING_PATTERN}"',
        )
        last_name = self._match_embedded_field(
            html_text,
            base_pattern + rf'"last_name":"{self.EMBEDDED_ESCAPED_STRING_PATTERN}"',
        ) or self._match_embedded_field(
            html_text,
            base_pattern + rf'"last_name_gen":"{self.EMBEDDED_ESCAPED_STRING_PATTERN}"',
        )
        domain = self._match_embedded_field(
            html_text,
            base_pattern + rf'"domain":"{self.EMBEDDED_ESCAPED_STRING_PATTERN}"',
        )
        avatar_url = self._match_embedded_field(
            html_text,
            base_pattern + rf'"photo_200":"{self.EMBEDDED_ESCAPED_STRING_PATTERN}"',
        ) or self._match_embedded_field(
            html_text,
            base_pattern + rf'"photo_max":"{self.EMBEDDED_ESCAPED_STRING_PATTERN}"',
        )
        country = self._match_embedded_field(
            html_text,
            base_pattern + rf'"country":\{{"id":\d+,"title":"{self.EMBEDDED_ESCAPED_STRING_PATTERN}"',
        )
        city = self._match_embedded_field(
            html_text,
            base_pattern + rf'"city":\{{"id":\d+,"title":"{self.EMBEDDED_ESCAPED_STRING_PATTERN}"',
        )
        status = self._match_embedded_field(
            html_text,
            base_pattern + rf'"status":"{self.EMBEDDED_ESCAPED_STRING_PATTERN}"',
        )

        display_name = self._first_non_empty(
            " ".join(part for part in (first_name, last_name) if isinstance(part, str) and part.strip()),
            first_name,
            domain,
        )
        canonical_url = f"https://vk.com/{domain}" if domain else None

        info_candidates = [country, city, status]
        info_lines = tuple(
            item for item in (self._normalize_info_line(value) for value in info_candidates) if item
        )
        return display_name, avatar_url, canonical_url, info_lines

    def _extract_embedded_community_identity(
        self,
        html_text: str,
        screen_name: str,
    ) -> tuple[Optional[str], Optional[str], Optional[str], tuple[str, ...]]:
        """Извлекает group/page identity из embedded payload."""
        escaped_screen_name = re.escape(screen_name.strip())
        base_pattern = rf'"screen_name":"{escaped_screen_name}".{{0,6000}}?'

        display_name = self._match_embedded_field(
            html_text,
            rf'"is_group_displayed":true.{{0,1200}}?"name":"{self.EMBEDDED_ESCAPED_STRING_PATTERN}".{{0,1200}}?"screen_name":"{escaped_screen_name}"',
        ) or self._match_embedded_field(
            html_text,
            rf'"name":"{self.EMBEDDED_ESCAPED_STRING_PATTERN}".{{0,1200}}?"screen_name":"{escaped_screen_name}".{{0,2400}}?"photo_200":"{self.EMBEDDED_ESCAPED_FRAGMENT_PATTERN}"',
        )
        avatar_url = self._match_embedded_field(
            html_text,
            base_pattern + rf'"photo_200":"{self.EMBEDDED_ESCAPED_STRING_PATTERN}"',
        ) or self._match_embedded_field(
            html_text,
            base_pattern + rf'"photo_base":"{self.EMBEDDED_ESCAPED_STRING_PATTERN}"',
        )
        description = self._match_embedded_field(
            html_text,
            base_pattern + rf'"description":"{self.EMBEDDED_ESCAPED_STRING_PATTERN}"',
        )
        site = self._match_embedded_field(
            html_text,
            base_pattern + rf'"site":"{self.EMBEDDED_ESCAPED_STRING_PATTERN}"',
        )

        info_lines = tuple(
            item for item in (self._normalize_info_line(value) for value in (description, site)) if item
        )
        return display_name, avatar_url, None, info_lines

    @classmethod
    def _build_caption(
        cls,
        *,
        title: str,
        canonical_url: str,
        screen_name: str,
        info_lines: tuple[str, ...],
    ) -> str:
        """Формирует профильную подпись: hyperlink + nickname + публичные строки."""
        safe_title = html.escape(cls._strip_vk_suffix(title))
        safe_url = html.escape(canonical_url, quote=True)
        lines = [f'<a href="{safe_url}"><b>{safe_title}</b></a>']
        normalized_screen_name = screen_name.strip().lstrip("@")
        safe_screen_name = html.escape(normalized_screen_name)
        normalized_title = cls._strip_vk_suffix(title).strip().lower()
        if safe_screen_name and normalized_title not in {normalized_screen_name.lower(), f"@{normalized_screen_name.lower()}"}:
            lines.append(f"@{safe_screen_name}")
        for item in info_lines:
            lines.append(f"• {html.escape(item)}")
        return "\n".join(lines)

    def _extract_title(
        self,
        soup: BeautifulSoup,
        *,
        screen_name: str,
        ld_display_name: Optional[str] = None,
    ) -> str:
        """Извлекает display title для profile/community."""
        if ld_display_name:
            return self._strip_vk_suffix(ld_display_name)

        og_title = soup.find("meta", attrs={"property": "og:title"})
        if og_title:
            candidate = self._first_non_empty(og_title.get("content"))
            if candidate:
                return self._strip_vk_suffix(candidate)

        html_title = self._first_non_empty(soup.title.get_text(strip=True) if soup.title else None)
        if html_title:
            stripped = self._strip_vk_suffix(html_title)
            if stripped == "ВКонтакте":
                return screen_name
            return stripped

        return screen_name or "VK Profile"

    async def process(
        self,
        session: aiohttp.ClientSession,
        original_url: str,
        context: str,
        canonical_url: str,
        screen_name: str,
    ) -> Optional[MediaResult]:
        """Возвращает profile-card для user/community URL."""
        html_text = await self._fetch_html(session, canonical_url)
        if not html_text:
            return None

        soup = BeautifulSoup(html_text, "html.parser")
        ld_display_name, ld_avatar_url, ld_canonical_url = self._extract_ld_identity(html_text)
        embedded_display_name: Optional[str] = None
        embedded_avatar_url: Optional[str] = None
        embedded_canonical_url: Optional[str] = None
        embedded_info_lines: tuple[str, ...] = ()

        account_identity = self._extract_embedded_account_identity(html_text, screen_name)
        if any(account_identity[:3]) or account_identity[3]:
            (
                embedded_display_name,
                embedded_avatar_url,
                embedded_canonical_url,
                embedded_info_lines,
            ) = account_identity
        else:
            (
                embedded_display_name,
                embedded_avatar_url,
                embedded_canonical_url,
                embedded_info_lines,
            ) = self._extract_embedded_community_identity(html_text, screen_name)

        title = self._extract_title(
            soup,
            screen_name=screen_name,
            ld_display_name=ld_display_name,
        )
        normalized_embedded_title = self._strip_vk_suffix(embedded_display_name) if embedded_display_name else None
        if (
            normalized_embedded_title
            and normalized_embedded_title.strip().lower() not in self.GENERIC_EMBEDDED_TITLES
            and title.strip().lower() in {screen_name.strip().lower(), "vk profile", "вконтакте"}
        ):
            title = normalized_embedded_title
        public_info = embedded_info_lines or self._extract_public_info(soup, html_text)

        avatar_url = None
        og_image = soup.find("meta", attrs={"property": "og:image"})
        if og_image:
            avatar_url = self._extract_first_http_url(og_image.get("content"))
        if not avatar_url:
            avatar_url = embedded_avatar_url or ld_avatar_url

        avatar_path = None
        if avatar_url:
            avatar_path = self._generate_unique_path(f"{screen_name}_avatar", suffix=".jpg")
            if not await self._download_thumbnail(avatar_url, avatar_path, self.photo_limit):
                avatar_path = None

        profile_url = embedded_canonical_url or ld_canonical_url or canonical_url
        effective_screen_name = screen_name
        if embedded_canonical_url:
            embedded_path = embedded_canonical_url.rstrip("/").rsplit("/", 1)[-1]
            if embedded_path:
                effective_screen_name = embedded_path

        return MediaResult(
            content_type=ContentType.PROFILE,
            source_name="VK",
            original_url=original_url,
            context=context,
            title=title,
            uploader=effective_screen_name,
            main_file_path=avatar_path,
            caption_text=self._build_caption(
                title=title,
                canonical_url=profile_url,
                screen_name=effective_screen_name,
                info_lines=public_info,
            ),
        )
