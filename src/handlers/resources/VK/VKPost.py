"""
Процессор VK wall posts.
"""

from __future__ import annotations

import html
import json
import logging
import re
from typing import Any, Optional

import aiohttp
from bs4 import BeautifulSoup

from src.handlers.contracts import (
    AttachmentKind,
    AudioAttachment,
    ContentType,
    MediaAttachment,
    MediaResult,
    normalize_cleanup_paths,
)
from .VKDependencies import VKMediaGatewayProtocol, VKRequestContextProtocol

logger = logging.getLogger(__name__)


class VKPost:
    """Процессор wall post с separate text + media payload extraction."""

    EMBEDDED_POST_MARKER = '"method":"wall.getById"'
    IMAGE_URL_PATTERN = re.compile(r'https?://[^"\']+\.(?:jpg|jpeg|png)[^"\']*', re.IGNORECASE)
    EMBEDDED_TEXT_PATTERN = re.compile(
        r'"text":"(?P<text>[^"\\]*(?:\\.[^"\\]*)*)"',
        re.DOTALL,
    )
    POST_TEXT_SELECTOR = (
        ".wall_post_text",
        ".pi_text",
        ".post_text",
        "[data-post-id] .wall_post_text",
    )
    POST_CAPTION_TITLE = "Посты из ленты"
    MAX_INLINE_IMAGES = 6
    MAX_LEAD_TEXT = 3900

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
    def _build_caption(title: str, canonical_url: str) -> str:
        """Формирует caption wall post."""
        safe_title = html.escape(title)
        safe_url = html.escape(canonical_url, quote=True)
        return f'<a href="{safe_url}"><b>{safe_title}</b></a>'

    @staticmethod
    def _strip_vk_suffix(title: str) -> str:
        """Убирает стандартные VK-суффиксы из заголовка страницы."""
        cleaned = title.strip()
        for suffix in ("| ВКонтакте", "— ВКонтакте", "- ВКонтакте"):
            if cleaned.endswith(suffix):
                cleaned = cleaned[: -len(suffix)].rstrip()
        return cleaned or title.strip()

    def _normalize_post_text(self, raw_text: str) -> Optional[str]:
        """Нормализует текст поста для отдельного Telegram-сообщения."""
        stripped = self._strip_html(raw_text) if isinstance(raw_text, str) else None
        if not stripped:
            return None

        normalized = html.unescape(stripped).replace("\r\n", "\n").replace("\r", "\n")
        lines = [re.sub(r"\s+", " ", line).strip() for line in normalized.split("\n")]
        compact_lines = [line for line in lines if line]
        if not compact_lines:
            return None

        joined = "\n".join(compact_lines)
        if len(joined) <= self.MAX_LEAD_TEXT:
            return joined
        return joined[: self.MAX_LEAD_TEXT - 3].rstrip() + "..."

    def _extract_title(self, soup: BeautifulSoup, owner_id: str, post_id: str) -> str:
        """Извлекает отображаемый заголовок поста."""
        og_title = soup.find("meta", attrs={"property": "og:title"})
        title_candidate = self._first_non_empty(og_title.get("content") if og_title else None)
        if title_candidate:
            return self._strip_vk_suffix(title_candidate)

        html_title = self._first_non_empty(soup.title.get_text(strip=True) if soup.title else None)
        if html_title:
            return self._strip_vk_suffix(html_title)

        return f"VK Post {owner_id}_{post_id}"

    @staticmethod
    def _decode_embedded_json_string(value: str) -> Optional[str]:
        """Декодирует JSON-escaped строку из embedded VK payload."""
        if not isinstance(value, str) or not value:
            return None
        try:
            return json.loads(f'"{value}"')
        except json.JSONDecodeError:
            return html.unescape(value.replace("\\n", "\n").replace("\\/", "/"))

    def _extract_prefetched_post_text(self, html_text: str) -> Optional[str]:
        """Извлекает текст поста из embedded `wall.getById` payload."""
        marker_index = html_text.find(self.EMBEDDED_POST_MARKER)
        if marker_index < 0:
            return None
        segment = html_text[marker_index : marker_index + 70000]

        candidates: list[str] = []
        for text_match in self.EMBEDDED_TEXT_PATTERN.finditer(segment):
            decoded = self._decode_embedded_json_string(text_match.group("text"))
            normalized = self._normalize_post_text(decoded or "")
            if not normalized:
                continue
            if normalized in {"Что-то пошло не так.", "Класс !!!"}:
                continue
            candidates.append(normalized)

        if not candidates:
            return None
        return max(candidates, key=len)

    def _extract_prefetched_owner_name(self, html_text: str, owner_id: str) -> Optional[str]:
        """Извлекает human-readable owner name из embedded groups/profiles blocks."""
        if owner_id.startswith("-"):
            group_id = owner_id.lstrip("-")
            pattern = re.compile(
                rf'"groups":\[(?P<section>.{{0,20000}}?"id":{group_id}.{{0,4000}}?"name":"(?P<name>[^"\\]*(?:\\.[^"\\]*)*)")',
                re.DOTALL,
            )
            match = pattern.search(html_text)
            if match:
                return self._decode_embedded_json_string(match.group("name"))
            return None

        profile_pattern = re.compile(
            rf'"profiles":\[(?P<section>.{{0,20000}}?"id":{owner_id}.{{0,4000}}?)',
            re.DOTALL,
        )
        profile_match = profile_pattern.search(html_text)
        if not profile_match:
            return None

        section = profile_match.group("section")
        first_name_match = re.search(r'"first_name":"(?P<value>[^"\\]*(?:\\.[^"\\]*)*)"', section)
        last_name_match = re.search(r'"last_name":"(?P<value>[^"\\]*(?:\\.[^"\\]*)*)"', section)
        first_name = self._decode_embedded_json_string(first_name_match.group("value")) if first_name_match else None
        last_name = self._decode_embedded_json_string(last_name_match.group("value")) if last_name_match else None
        display_name = " ".join(
            part for part in (first_name, last_name) if isinstance(part, str) and part.strip()
        ).strip()
        return display_name or first_name or last_name

    def _extract_prefetched_post_photo_url(self, html_text: str, post_id: str) -> Optional[str]:
        """Извлекает URL основной картинки поста из embedded wall payload."""
        marker_index = html_text.find(self.EMBEDDED_POST_MARKER)
        if marker_index < 0:
            return None
        segment = html_text[marker_index : marker_index + 90000]

        post_pattern = re.compile(
            rf'"id":{post_id}.{{0,15000}}?"orig_photo":\{{[^}}]*"url":"(?P<url>[^"\\]*(?:\\.[^"\\]*)*)"',
            re.DOTALL,
        )
        match = post_pattern.search(segment)
        if not match:
            return None
        return self._decode_embedded_json_string(match.group("url"))

    @staticmethod
    def _should_prefer_embedded_photo(
        media_group: list[MediaAttachment],
        audios: list[AudioAttachment],
    ) -> bool:
        """Предпочитает embedded original-photo для одиночного photo-post."""
        if audios:
            return False
        if not media_group:
            return True
        return len(media_group) == 1 and media_group[0].kind == AttachmentKind.PHOTO

    async def _download_embedded_post_photo(
        self,
        *,
        html_text: str,
        post_id: str,
        post_token: str,
    ) -> Optional[MediaAttachment]:
        """Скачивает original photo из embedded wall payload, если она есть."""
        embedded_photo_url = self._extract_prefetched_post_photo_url(html_text, post_id)
        if not embedded_photo_url:
            return None

        embedded_photo_path = self._generate_unique_path(f"{post_token}_embedded", suffix=".jpg")
        if not await self._download_thumbnail(embedded_photo_url, embedded_photo_path, self.photo_limit):
            return None
        return MediaAttachment(kind=AttachmentKind.PHOTO, file_path=embedded_photo_path)

    def _extract_post_text(self, soup: BeautifulSoup, html_text: str, title: str) -> Optional[str]:
        """Извлекает текст поста из HTML/JSON-LD с graceful fallback."""
        candidates: list[str] = []

        for payload in self._extract_ld_objects(html_text):
            for key in ("articleBody", "text", "description"):
                value = payload.get(key)
                if isinstance(value, str):
                    normalized = self._normalize_post_text(value)
                    if normalized:
                        candidates.append(normalized)

        for selector in self.POST_TEXT_SELECTOR:
            for node in soup.select(selector):
                normalized = self._normalize_post_text(node.get_text("\n", strip=True))
                if normalized:
                    candidates.append(normalized)

        for attrs in (
            {"property": "og:description"},
            {"name": "description"},
        ):
            node = soup.find("meta", attrs=attrs)
            if node:
                normalized = self._normalize_post_text(str(node.get("content") or ""))
                if normalized:
                    candidates.append(normalized)

        cleaned_candidates: list[str] = []
        seen: set[str] = set()
        lowered_title = title.strip().lower()
        for candidate in candidates:
            normalized = candidate.strip()
            if not normalized:
                continue
            lowered = normalized.lower()
            if lowered == lowered_title:
                continue
            if lowered in seen:
                continue
            seen.add(lowered)
            cleaned_candidates.append(normalized)

        if not cleaned_candidates:
            return self._extract_prefetched_post_text(html_text)
        return max(cleaned_candidates, key=len)

    async def _download_media_payload(
        self,
        *,
        original_url: str,
        canonical_url: str,
        post_token: str,
    ) -> Optional[list[dict[str, Any]]]:
        """Пытается получить media payload поста через yt-dlp media-group path."""
        ydl_opts: dict[str, Any] = {
            "format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/bestaudio/best",
            "ignoreerrors": True,
            "extract_flat": False,
            "noplaylist": False,
            "writethumbnail": False,
            "retries": 2,
            "fragment_retries": 2,
            "geo_bypass": True,
            "user_agent": self.DEFAULT_USER_AGENT,
            "http_headers": self.build_browser_headers(referer=canonical_url),
        }
        ydl_opts.update(self._build_vk_cookie_opts())

        candidate_urls = tuple(
            dict.fromkeys(
                (
                    canonical_url,
                    self._normalize_vk_url(original_url),
                )
            )
        )
        for candidate_url in candidate_urls:
            payload = await self._download_media_group(
                candidate_url,
                ydl_opts,
                group_id=post_token,
            )
            if isinstance(payload, list) and payload:
                return payload
        return None

    async def _extract_inline_images(
        self,
        *,
        html_text: str,
        post_token: str,
    ) -> tuple[MediaAttachment, ...]:
        """Fallback: вытаскивает inline photo URLs из HTML, если yt-dlp не вернул payload."""
        media_group: list[MediaAttachment] = []
        seen_urls: set[str] = set()
        for image_url in self.IMAGE_URL_PATTERN.findall(html_text):
            normalized_url = image_url.replace("http://", "https://", 1)
            lowered_url = normalized_url.lower()
            if normalized_url in seen_urls:
                continue
            if any(marker in lowered_url for marker in ("emoji", "sprite", "logo", "icon")):
                continue
            seen_urls.add(normalized_url)
            file_path = self._generate_unique_path(f"{post_token}_{len(media_group)}", suffix=".jpg")
            if await self._download_thumbnail(normalized_url, file_path, self.photo_limit):
                media_group.append(MediaAttachment(kind=AttachmentKind.PHOTO, file_path=file_path))
            if len(media_group) >= self.MAX_INLINE_IMAGES:
                break
        return tuple(media_group)

    async def process(
        self,
        session: aiohttp.ClientSession,
        original_url: str,
        context: str,
        owner_id: str,
        post_id: str,
    ) -> Optional[MediaResult]:
        """Возвращает post payload: отдельный текст + media/audios, если доступны."""
        canonical_url = f"https://vk.com/wall{owner_id}_{post_id}"
        html_text = await self._fetch_html(session, canonical_url)
        if not html_text:
            return None

        soup = BeautifulSoup(html_text, "html.parser")
        title = self._extract_title(soup, owner_id=owner_id, post_id=post_id)
        lead_text = self._extract_post_text(soup, html_text, title=title)
        owner_label = self._extract_prefetched_owner_name(html_text, owner_id) or owner_id

        post_token = f"wall{owner_id}_{post_id}"
        media_group: list[MediaAttachment] = []
        audios: list[AudioAttachment] = []
        extra_cleanup_paths = []

        payload = await self._download_media_payload(
            original_url=original_url,
            canonical_url=canonical_url,
            post_token=post_token,
        )
        if payload:
            seen_paths: set[str] = set()
            for item in payload:
                file_path = item.get("file_path")
                if not hasattr(file_path, "exists") or not file_path.exists():
                    continue
                if file_path.stat().st_size <= 0:
                    continue

                resolved_path = str(file_path.resolve())
                if resolved_path in seen_paths:
                    continue
                seen_paths.add(resolved_path)

                item_type = str(item.get("type") or "").strip().lower()
                if item_type == "photo":
                    media_group.append(MediaAttachment(kind=AttachmentKind.PHOTO, file_path=file_path))
                    continue
                if item_type == "audio":
                    audios.append(AudioAttachment(file_path=file_path))
                    continue
                media_group.append(MediaAttachment(kind=AttachmentKind.VIDEO, file_path=file_path))

        embedded_photo = await self._download_embedded_post_photo(
            html_text=html_text,
            post_id=post_id,
            post_token=post_token,
        )
        if embedded_photo is not None:
            if self._should_prefer_embedded_photo(media_group, audios):
                extra_cleanup_paths.extend(item.file_path for item in media_group)
                media_group = [embedded_photo]
            else:
                extra_cleanup_paths.append(embedded_photo.file_path)

        if not media_group and not audios:
            fallback_media = await self._extract_inline_images(html_text=html_text, post_token=post_token)
            media_group.extend(fallback_media)

        if not media_group and not audios:
            return None

        uploader = owner_label
        if payload and isinstance(payload[0], dict):
            info = payload[0].get("info")
            if isinstance(info, dict):
                uploader = self._first_non_empty(
                    info.get("uploader"),
                    info.get("channel"),
                    owner_label,
                    info.get("uploader_id"),
                    owner_id,
                ) or owner_label

        enriched_audios = tuple(
            AudioAttachment(
                file_path=audio_item.file_path,
                title=self.POST_CAPTION_TITLE,
                performer=uploader,
            )
            for audio_item in audios
        )

        return MediaResult(
            content_type=ContentType.MEDIA_GROUP,
            source_name="VK",
            original_url=original_url,
            context=context,
            title=self.POST_CAPTION_TITLE,
            uploader=uploader,
            caption_text=self._build_caption(title=owner_label, canonical_url=canonical_url),
            lead_text=lead_text,
            media_group=tuple(media_group),
            audios=enriched_audios,
            audio=enriched_audios[0] if enriched_audios else None,
            cleanup_paths=normalize_cleanup_paths(extra_cleanup_paths),
        )
