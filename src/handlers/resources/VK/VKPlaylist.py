"""
Процессор обработчика VK Music для плейлистов.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Iterable, Optional, Sequence

import aiohttp
from bs4 import BeautifulSoup

from src.handlers.contracts import ContentType, MediaResult
from .VKDependencies import VKMediaGatewayProtocol, VKRequestContextProtocol

logger = logging.getLogger(__name__)


class VKPlaylist:
    """
    Процессор для обработки плейлистов VK Music.
    """

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
    AUDIO_INDEX_TITLE = 3
    AUDIO_INDEX_PERFORMER = 4
    AUDIO_INDEX_DURATION = 5
    AUDIO_INDEX_COVER_URL = 14
    AUDIO_INDEX_ACCESS_KEY = 24
    VK_PLAYLIST_CONTEXT = "audio_page"
    VK_MAX_PLAYLIST_PAGES = 20

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

    def _looks_like_audio_tuple(self, value: Any) -> bool:
        """Проверяет, похож ли объект на tuple-аудио VK."""
        if not isinstance(value, list) or len(value) <= self.AUDIO_INDEX_DURATION:
            return False
        owner_id = self._safe_int(value[self.AUDIO_INDEX_OWNER_ID])
        audio_id = self._safe_int(value[self.AUDIO_INDEX_ID])
        return owner_id is not None and audio_id is not None

    def _extract_cover_url_from_audio_tuple(self, audio_tuple: Sequence[Any]) -> Optional[str]:
        """Извлекает URL обложки из tuple-аудио."""
        if len(audio_tuple) <= self.AUDIO_INDEX_COVER_URL:
            return None

        raw_cover = audio_tuple[self.AUDIO_INDEX_COVER_URL]
        if isinstance(raw_cover, str):
            for candidate in raw_cover.split(","):
                cleaned = candidate.strip()
                if cleaned.startswith(("http://", "https://")):
                    return cleaned

        return self._extract_first_http_url(raw_cover)

    def _audio_tuple_to_track_preview(self, audio_tuple: Sequence[Any]) -> dict[str, Any]:
        """Преобразует tuple-аудио в metadata-трек для playlist preview."""
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

    @classmethod
    def _extract_playlist_object_from_payload(cls, payload: Any) -> Optional[dict[str, Any]]:
        """
        Извлекает объект playlist из ответа `load_section`.
        """
        if isinstance(payload, list) and len(payload) > 1 and isinstance(payload[1], list) and payload[1]:
            first_item = payload[1][0]
            if isinstance(first_item, dict) and isinstance(first_item.get("list"), list):
                return first_item

        def _walk(value: Any) -> Iterable[dict[str, Any]]:
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
    ) -> Optional[dict[str, Any]]:
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
    ) -> Optional[dict[str, Any]]:
        """
        Загружает плейлист через API-цепочку `load_section` c поддержкой пагинации.
        """
        playlist_meta: Optional[dict[str, Any]] = None
        tracks: list[list[Any]] = []
        seen_track_ids: set[tuple[int, int]] = set()

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

    def _build_playlist_candidates(self, owner_id: str, playlist_id: str, access_hash: Optional[str]) -> tuple[str, ...]:
        """
        Возвращает VK URL-кандидаты плейлиста для web/mobile extraction.
        """
        token = self._build_playlist_token(owner_id, playlist_id, access_hash)
        return (f"https://vk.com/music/playlist/{token}",)

    @classmethod
    def _iter_playlist_track_nodes(cls, value: Any) -> Iterable[dict[str, Any]]:
        """
        Итерирует track-объекты из JSON-LD playlist структуры.
        """
        if isinstance(value, dict):
            if "item" in value:
                yield from cls._iter_playlist_track_nodes(value.get("item"))
                return
            if "track" in value and isinstance(value.get("track"), (dict, list)):
                yield from cls._iter_playlist_track_nodes(value.get("track"))
                return
            yield value
            return

        if isinstance(value, list):
            for item in value:
                yield from cls._iter_playlist_track_nodes(item)

    def _extract_playlist_metadata(self, html_text: str, canonical_url: str) -> dict[str, Any]:
        """
        Извлекает метаданные плейлиста и список треков без скачивания.
        """
        soup = BeautifulSoup(html_text, "html.parser")

        playlist_title = "VK Music Playlist"
        owner = "Unknown"
        tracks: list[dict[str, Any]] = []
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
        tracks: Sequence[dict[str, Any]],
    ) -> str:
        """
        Формирует текст превью плейлиста для Telegram.
        """
        lines = [
            f"{playlist_title}",
            f"Автор: {owner}",
            f"Треков: {track_count}",
        ]

        if tracks:
            lines.append("")
            lines.append("Первые треки:")
            for index, track in enumerate(tracks[:5], start=1):
                title = str(track.get("title") or "VK Track")
                performer = str(track.get("performer") or "Unknown")
                lines.append(f"{index}. {performer} - {title}")

        return "\n".join(lines)

    async def process(
        self,
        session: aiohttp.ClientSession,
        original_url: str,
        context: str,
        owner_id: str,
        playlist_id: str,
        access_hash: Optional[str],
    ) -> Optional[MediaResult]:
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
                return MediaResult(
                    content_type=ContentType.PLAYLIST,
                    source_name="VK",
                    original_url=original_url,
                    context=context,
                    title=playlist_title,
                    uploader=playlist_owner,
                    caption_text=caption_text,
                )

            logger.warning("VK playlist API returned no tracks, fallback to HTML parsing: %s", canonical_url)

        candidate_urls = self._build_playlist_candidates(owner_id, playlist_id, access_hash)
        best_metadata: Optional[dict[str, Any]] = None
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

        return MediaResult(
            content_type=ContentType.PLAYLIST,
            source_name="VK",
            original_url=original_url,
            context=context,
            title=playlist_title,
            uploader=playlist_owner,
            caption_text=caption_text,
        )
