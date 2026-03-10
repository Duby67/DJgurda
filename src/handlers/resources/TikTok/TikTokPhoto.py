"""
Процессор фото и слайдшоу TikTok.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlsplit

import aiohttp

from src.handlers.contracts import (
    AttachmentKind,
    AudioAttachment,
    ContentType,
    MediaAttachment,
    MediaResult,
)

from .TikTokDependencies import TikTokMediaGatewayProtocol, TikTokOptionsProviderProtocol

logger = logging.getLogger(__name__)


class TikTokPhoto:
    """Процессор для обработки фото и слайдшоу TikTok."""

    TIKWM_API_URL = "https://www.tikwm.com/api/"
    TIKWM_TIMEOUT = 20
    DEFAULT_BACKGROUND_TRACK_TITLE = "Фоновая музыка TikTok"
    DEFAULT_BACKGROUND_TRACK_PERFORMER = "TikTok"

    def __init__(
        self,
        *,
        media_gateway: TikTokMediaGatewayProtocol,
        options_provider: TikTokOptionsProviderProtocol,
    ) -> None:
        self._media_gateway = media_gateway
        self._options_provider = options_provider

    @staticmethod
    def _suffix_from_url(media_url: str, default_suffix: str) -> str:
        """Возвращает расширение файла из URL или дефолтное значение."""
        suffix = Path(urlsplit(media_url).path).suffix.lower()
        if not suffix or len(suffix) > 5:
            return default_suffix
        return suffix

    def _extract_music_metadata_from_tikwm(self, media_data: dict[str, Any]) -> dict[str, str]:
        """Извлекает название трека и исполнителя из payload TikWM."""
        music_info = media_data.get("music_info") if isinstance(media_data, dict) else None
        music_info = music_info if isinstance(music_info, dict) else {}

        track_title = music_info.get("title")
        track_author = music_info.get("author")

        if not isinstance(track_title, str) or not track_title.strip():
            track_title = self.DEFAULT_BACKGROUND_TRACK_TITLE
        if not isinstance(track_author, str) or not track_author.strip():
            track_author = self.DEFAULT_BACKGROUND_TRACK_PERFORMER

        return {
            "title": track_title.strip(),
            "performer": track_author.strip(),
        }

    @staticmethod
    def _extract_first_http_url(value: Any) -> Optional[str]:
        """Пытается извлечь первый HTTP(S)-URL из произвольной структуры."""
        if isinstance(value, str):
            return value if value.startswith(("http://", "https://")) else None

        if isinstance(value, (list, tuple)):
            for item in value:
                found = TikTokPhoto._extract_first_http_url(item)
                if found:
                    return found
            return None

        if isinstance(value, dict):
            preferred_keys = (
                "url",
                "src",
                "cover",
                "cover_url",
                "cover_hd",
                "origin_cover",
                "thumbnail",
                "thumb",
            )
            for key in preferred_keys:
                if key in value:
                    found = TikTokPhoto._extract_first_http_url(value.get(key))
                    if found:
                        return found
            for nested_value in value.values():
                found = TikTokPhoto._extract_first_http_url(nested_value)
                if found:
                    return found
            return None

        return None

    def _extract_music_cover_url_from_tikwm(self, media_data: dict[str, Any]) -> Optional[str]:
        """Извлекает URL обложки трека из payload TikWM."""
        if not isinstance(media_data, dict):
            return None

        candidates = [
            media_data.get("music_info"),
            media_data.get("music_cover"),
            media_data.get("cover"),
            media_data.get("origin_cover"),
            media_data.get("ai_dynamic_cover"),
        ]
        for candidate in candidates:
            found = self._extract_first_http_url(candidate)
            if found:
                return found
        return None

    def _extract_music_metadata_from_info(self, info: dict[str, Any]) -> dict[str, str]:
        """Извлекает название трека и исполнителя из данных yt-dlp."""
        if not isinstance(info, dict):
            return {
                "title": self.DEFAULT_BACKGROUND_TRACK_TITLE,
                "performer": self.DEFAULT_BACKGROUND_TRACK_PERFORMER,
            }

        track_title = info.get("track")
        track_author = None

        artists = info.get("artists")
        if isinstance(artists, list):
            for artist in artists:
                if isinstance(artist, str) and artist.strip():
                    track_author = artist.strip()
                    break

        if not track_author:
            artist = info.get("artist")
            if isinstance(artist, str) and artist.strip():
                track_author = artist.strip()

        if not isinstance(track_title, str) or not track_title.strip():
            track_title = self.DEFAULT_BACKGROUND_TRACK_TITLE
        if not isinstance(track_author, str) or not track_author.strip():
            track_author = self.DEFAULT_BACKGROUND_TRACK_PERFORMER

        return {
            "title": track_title.strip(),
            "performer": track_author.strip(),
        }

    def _extract_music_cover_url_from_info(self, info: dict[str, Any]) -> Optional[str]:
        """Извлекает URL обложки трека из данных yt-dlp."""
        if not isinstance(info, dict):
            return None

        candidates = [
            info.get("thumbnail"),
            info.get("thumbnails"),
            info.get("cover"),
            info.get("album_art"),
            info.get("artwork_url"),
        ]
        for candidate in candidates:
            found = self._extract_first_http_url(candidate)
            if found:
                return found
        return None

    async def _fetch_tikwm_payload(self, target_url: str) -> Optional[dict[str, Any]]:
        """Получает данные о photo/slideshow посте через внешний API TikWM."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.tikwm.com/",
        }
        payload = {"url": target_url, "hd": "1"}

        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.post(
                    self.TIKWM_API_URL,
                    data=payload,
                    timeout=self.TIKWM_TIMEOUT,
                ) as resp:
                    if resp.status != 200:
                        logger.warning("TikWM API HTTP %s for %s", resp.status, target_url)
                        return None
                    data = await resp.json(content_type=None)
        except Exception as exc:  # noqa: BLE001
            logger.warning("TikWM API request failed for %s: %s", target_url, exc)
            return None

        if not isinstance(data, dict):
            logger.warning("TikWM API returned invalid payload type for %s", target_url)
            return None

        if data.get("code") != 0:
            logger.warning("TikWM API returned code=%s for %s", data.get("code"), target_url)
            return None

        media_data = data.get("data")
        if not isinstance(media_data, dict):
            logger.warning("TikWM API returned invalid data field for %s", target_url)
            return None

        return media_data

    async def _build_from_tikwm_payload(
        self,
        *,
        target_url: str,
        original_url: str,
        context: str,
        photo_id: str,
    ) -> Optional[MediaResult]:
        """Формирует typed-результат на основе данных TikWM."""
        media_data = await self._fetch_tikwm_payload(target_url)
        if not media_data:
            return None

        image_urls = [
            image_url
            for image_url in media_data.get("images", [])
            if isinstance(image_url, str) and image_url.startswith("http")
        ]
        if not image_urls:
            logger.warning("TikWM returned no images for %s", target_url)
            return None

        photos: list[Path] = []
        for index, image_url in enumerate(image_urls, start=1):
            photo_path = self._media_gateway.generate_unique_path(
                f"{photo_id}_photo_{index}",
                suffix=self._suffix_from_url(image_url, ".jpg"),
            )
            if await self._media_gateway.download_photo(
                image_url,
                photo_path,
                size_limit=self._media_gateway.photo_limit,
            ):
                photos.append(photo_path)

        if not photos:
            logger.error("Failed to download photos from TikWM payload for %s", target_url)
            return None

        title = media_data.get("title") or "TikTok Photo"
        author_info = media_data.get("author") if isinstance(media_data.get("author"), dict) else {}
        uploader = (
            author_info.get("nickname")
            or author_info.get("unique_id")
            or author_info.get("id")
            or "Unknown"
        )

        music_url = media_data.get("music")
        has_music = isinstance(music_url, str) and music_url.startswith("http")

        if len(photos) == 1 and not has_music:
            return MediaResult(
                content_type=ContentType.PHOTO,
                source_name="TikTok",
                original_url=original_url,
                context=context,
                title=title,
                uploader=uploader,
                main_file_path=photos[0],
                thumbnail_path=None,
            )

        audio_attachment = None
        if has_music:
            music_meta = self._extract_music_metadata_from_tikwm(media_data)
            audio_path = self._media_gateway.generate_unique_path(
                f"{photo_id}_audio",
                suffix=self._suffix_from_url(music_url, ".m4a"),
            )
            if await self._media_gateway.download_audio(
                music_url,
                audio_path,
                size_limit=self._media_gateway.audio_limit,
            ):
                audio_thumbnail_path = None
                music_cover_url = self._extract_music_cover_url_from_tikwm(media_data)
                if music_cover_url:
                    cover_path = self._media_gateway.generate_unique_path(
                        f"{photo_id}_audio_cover",
                        suffix=self._suffix_from_url(music_cover_url, ".jpg"),
                    )
                    if await self._media_gateway.download_thumbnail(
                        music_cover_url,
                        cover_path,
                        size_limit=self._media_gateway.photo_limit,
                    ):
                        audio_thumbnail_path = cover_path
                    else:
                        logger.warning("Failed to download TikTok music cover for %s", target_url)

                audio_attachment = AudioAttachment(
                    file_path=audio_path,
                    title=music_meta["title"],
                    performer=music_meta["performer"],
                    thumbnail_path=audio_thumbnail_path,
                )
            else:
                logger.warning("Failed to download TikTok music for %s", target_url)

        return MediaResult(
            content_type=ContentType.MEDIA_GROUP,
            source_name="TikTok",
            original_url=original_url,
            context=context,
            title=title,
            uploader=uploader,
            media_group=tuple(
                MediaAttachment(kind=AttachmentKind.PHOTO, file_path=photo_path)
                for photo_path in photos
            ),
            audio=audio_attachment,
            audios=(audio_attachment,) if audio_attachment is not None else (),
        )

    async def process(
        self,
        url: str,
        context: str,
        original_url: str,
    ) -> Optional[MediaResult]:
        """Обрабатывает фото/слайдшоу и возвращает typed `MediaResult`."""
        photo_id_match = re.search(r"/(\d+)[?/]?", url)
        photo_id = photo_id_match.group(1) if photo_id_match else "unknown"

        tikwm_result = await self._build_from_tikwm_payload(
            target_url=url,
            original_url=original_url,
            context=context,
            photo_id=photo_id,
        )
        if tikwm_result:
            return tikwm_result

        logger.warning("TikWM fallback failed for %s, trying yt-dlp", url)

        ydl_opts: dict[str, Any] = {
            "format": "bestaudio/best",
            "writethumbnail": False,
            "extract_flat": False,
            "ignoreerrors": True,
            "playlistend": None,
            "extractor_args": {
                "tiktok": {
                    "api_hostname": "www.tiktok.com",
                    "extract_flat": False,
                    "webpage_fallback": False,
                }
            },
            "force_generic_extractor": False,
        }
        ydl_opts.update(self._options_provider.build_ytdlp_opts())

        media_list = await self._media_gateway.download_media_group(
            url,
            ydl_opts,
            group_id=photo_id,
            size_limit=self._media_gateway.photo_limit,
        )

        if not media_list and "/photo/" in url:
            fallback_url = re.sub(
                r"^https?://(?:m\.)?tiktok\.com",
                "https://www.tiktok.com",
                url,
                count=1,
            ).replace("/photo/", "/video/", 1)
            logger.warning("Trying ytdlp fallback URL: %s -> %s", url, fallback_url)
            media_list = await self._media_gateway.download_media_group(
                fallback_url,
                ydl_opts,
                group_id=photo_id,
                size_limit=self._media_gateway.photo_limit,
            )

        if not media_list:
            logger.error("Failed to download media from TikTok post")
            return None

        photos = [item for item in media_list if item.get("type") == "photo"]
        audios = [item for item in media_list if item.get("type") == "audio"]
        if not photos and not audios:
            logger.error("TikTok photo processing produced no photos and no audio")
            return None

        first_info = media_list[0].get("info", {})
        if not isinstance(first_info, dict):
            first_info = {}
        title = first_info.get("title", "TikTok Photo")
        uploader = first_info.get("uploader", first_info.get("channel", "Unknown"))

        if len(photos) == 1 and not audios:
            file_path = photos[0].get("file_path")
            if file_path is None:
                return None
            return MediaResult(
                content_type=ContentType.PHOTO,
                source_name="TikTok",
                original_url=original_url,
                context=context,
                title=title,
                uploader=uploader,
                main_file_path=file_path,
                thumbnail_path=None,
            )

        media_group = tuple(
            MediaAttachment(kind=AttachmentKind.PHOTO, file_path=item["file_path"])
            for item in photos
            if item.get("file_path") is not None
        )

        audio_attachment = None
        if audios:
            music_meta = self._extract_music_metadata_from_info(first_info)
            audio_file = audios[0].get("file_path")
            if audio_file is not None:
                audio_source_info = audios[0].get("info", {})
                if not isinstance(audio_source_info, dict):
                    audio_source_info = first_info
                audio_thumbnail_path = None

                music_cover_url = self._extract_music_cover_url_from_info(audio_source_info)
                if music_cover_url:
                    cover_path = self._media_gateway.generate_unique_path(
                        f"{photo_id}_audio_cover",
                        suffix=self._suffix_from_url(music_cover_url, ".jpg"),
                    )
                    if await self._media_gateway.download_thumbnail(
                        music_cover_url,
                        cover_path,
                        size_limit=self._media_gateway.photo_limit,
                    ):
                        audio_thumbnail_path = cover_path
                    else:
                        logger.warning("Failed to download ytdlp music cover for %s", url)

                audio_attachment = AudioAttachment(
                    file_path=audio_file,
                    title=music_meta["title"],
                    performer=music_meta["performer"],
                    thumbnail_path=audio_thumbnail_path,
                )

        return MediaResult(
            content_type=ContentType.MEDIA_GROUP,
            source_name="TikTok",
            original_url=original_url,
            context=context,
            title=title,
            uploader=uploader,
            media_group=media_group,
            audio=audio_attachment,
            audios=(audio_attachment,) if audio_attachment is not None else (),
        )