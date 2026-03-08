"""
Миксин обработчика VK Music для плейлистов.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Iterable, Optional, Sequence, Tuple

import aiohttp
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class VKPlaylist:
    """
    Миксин для обработки плейлистов VK Music.
    """

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

    @classmethod
    def _build_playlist_candidates(cls, owner_id: str, playlist_id: str, access_hash: Optional[str]) -> tuple[str, ...]:
        """
        Возвращает VK URL-кандидаты плейлиста для web/mobile extraction.
        """
        token = cls._build_playlist_token(owner_id, playlist_id, access_hash)
        return (f"https://vk.com/music/playlist/{token}",)

    @classmethod
    def _iter_playlist_track_nodes(cls, value: Any) -> Iterable[Dict[str, Any]]:
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
