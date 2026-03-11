"""Typed-обработчик ссылок Yandex Music (`track`)."""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Any, Optional

from yandex_music import Client

from src.config import PROJECT_TEMP_DIR, YANDEX_MUSIC_TOKEN
from src.handlers.base import BaseHandler
from src.handlers.contracts import AudioAttachment, ContentType, MediaResult
from src.handlers.infrastructure import DelayPolicyService, HttpFileService, RuntimePathService

logger = logging.getLogger(__name__)


class YandexMusicHandler(BaseHandler):
    """Обработчик ссылок Yandex Music (`/track/<id>`)."""

    PATTERN = re.compile(
        r"https?://(?:music\.yandex\.(?:ru|by|kz|ua)/|yandex\.ru/music/)\S+"
    )
    TRACK_ID_PATTERN = re.compile(r"/track/(\d+)")

    def __init__(self) -> None:
        self._runtime_dir = PROJECT_TEMP_DIR / self.__class__.__name__
        self._runtime_dir.mkdir(parents=True, exist_ok=True)

        if not YANDEX_MUSIC_TOKEN:
            logger.error("YANDEX_MUSIC_TOKEN is not set. Yandex Music handler will not work.")

        self._token = YANDEX_MUSIC_TOKEN
        self._client: Client | None = None
        self._lock = asyncio.Lock()
        self._runtime_paths = RuntimePathService(runtime_dir=self._runtime_dir)
        self._http_service = HttpFileService(delay_policy=DelayPolicyService())

    @property
    def pattern(self) -> re.Pattern:
        return self.PATTERN

    @property
    def source_name(self) -> str:
        return "Yandex.Music"

    async def _get_client(self) -> Client:
        if self._client is None:
            self._client = await asyncio.to_thread(lambda: Client(self._token).init())
        return self._client

    @classmethod
    def _extract_track_id(cls, url: str) -> str | None:
        match = cls.TRACK_ID_PATTERN.search(url)
        return match.group(1) if match else None

    @staticmethod
    def _extract_artists(track: Any) -> str:
        artists = getattr(track, "artists", None)
        if not artists:
            return "Unknown Artist"
        names = [artist.name for artist in artists if getattr(artist, "name", None)]
        return ", ".join(names) if names else "Unknown Artist"

    async def _get_best_direct_link(self, track: Any) -> str | None:
        download_info = await asyncio.to_thread(track.get_download_info)
        if not download_info:
            return None

        best = max(download_info, key=lambda item: getattr(item, "bitrate_in_kbps", 0) or 0)
        direct_link = await asyncio.to_thread(best.get_direct_link)
        return direct_link if isinstance(direct_link, str) and direct_link else None

    async def _get_cover_file(self, cover_uri: str, *, track_id: str) -> Path | None:
        if not cover_uri:
            return None

        cover_url = f"https://{cover_uri.replace('%%', '400x400')}"
        cover_path = self._runtime_paths.generate_unique_path(f"cover_{track_id}", suffix=".jpg")
        if await self._http_service.download_thumbnail(cover_url, cover_path):
            return cover_path
        return None

    async def process(
        self,
        url: str,
        context: str,
        resolved_url: Optional[str] = None,
    ) -> Optional[MediaResult]:
        if not self._token:
            logger.error("Skipping processing: Yandex Music token is missing")
            return None

        # Для устойчивости сначала берем ID из исходной ссылки пользователя,
        # а `resolved_url` используем как fallback (например, после redirect-цепочек).
        track_id = self._extract_track_id(url)
        if not track_id and resolved_url:
            track_id = self._extract_track_id(resolved_url)
        if not track_id:
            logger.error(
                "Failed to extract track ID from URLs: original=%s resolved=%s",
                url,
                resolved_url,
            )
            return None

        file_path: Path | None = None
        cover_path: Path | None = None
        try:
            async with self._lock:
                client = await self._get_client()
                tracks = await asyncio.to_thread(client.tracks, [track_id])
                if not tracks:
                    logger.error("Track %s not found", track_id)
                    return None

                track = tracks[0]
                title = getattr(track, "title", None) or f"Track {track_id}"
                artists = self._extract_artists(track)
                direct_link = await self._get_best_direct_link(track)
                if not direct_link:
                    logger.error("No direct download link for track %s", track_id)
                    return None

                file_path = self._runtime_paths.generate_unique_path(
                    f"yandex_track_{track_id}",
                    suffix=".mp3",
                )
                cover_uri = getattr(track, "cover_uri", None)

            if not await self._http_service.download_audio(direct_link, file_path):
                return None

            if isinstance(cover_uri, str) and cover_uri:
                cover_path = await self._get_cover_file(cover_uri, track_id=track_id)

            audio_item = AudioAttachment(
                file_path=file_path,
                title=title,
                performer=artists,
                thumbnail_path=cover_path,
            )

            logger.info("Yandex Music track downloaded: %s", file_path)
            return MediaResult(
                content_type=ContentType.AUDIO,
                source_name=self.source_name,
                original_url=url,
                context=context,
                title=title,
                uploader=artists,
                main_file_path=file_path,
                thumbnail_path=cover_path,
                audio=audio_item,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to download Yandex Music track: %s", exc)
            if file_path is not None:
                file_path.unlink(missing_ok=True)
            if cover_path is not None:
                cover_path.unlink(missing_ok=True)
            return None
