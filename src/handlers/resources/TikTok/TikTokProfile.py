"""
Процессор профилей TikTok.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

import aiohttp

from src.handlers.contracts import ContentType, MediaResult

from .TikTokDependencies import TikTokMediaGatewayProtocol

logger = logging.getLogger(__name__)


class TikTokProfile:
    """Процессор для обработки профилей TikTok."""

    def __init__(self, *, media_gateway: TikTokMediaGatewayProtocol) -> None:
        self._media_gateway = media_gateway

    async def _extract_profile_info(self, url: str) -> Optional[dict[str, Any]]:
        """Извлекает информацию о профиле TikTok из HTML страницы."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=15) as resp:
                    if resp.status != 200:
                        logger.error("HTTP %s while loading TikTok profile", resp.status)
                        return None
                    html = await resp.text()

            pattern = r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__" type="application/json">(.*?)</script>'
            match = re.search(pattern, html, re.DOTALL)
            if not match:
                logger.error("TikTok profile JSON not found")
                return None

            data = json.loads(match.group(1))

            user_info = data.get("__DEFAULT_SCOPE__", {}).get("webapp.user-detail", {}).get("userInfo", {})
            if not user_info:
                user_info = data.get("UserModule", {}).get("users", {})
                if user_info and isinstance(user_info, dict):
                    usernames = list(user_info.keys())
                    if not usernames:
                        logger.error("Empty users block in UserModule")
                        return None
                    user_info = user_info[usernames[0]]
                else:
                    logger.error("Failed to extract userInfo from JSON")
                    return None

            stats = user_info.get("stats", {})
            user = user_info.get("user", {})

            return {
                "unique_id": user.get("uniqueId"),
                "nickname": user.get("nickname"),
                "signature": user.get("signature", ""),
                "avatar_url": user.get("avatarLarger") or user.get("avatarMedium") or user.get("avatarThumb"),
                "follower_count": stats.get("followerCount", 0),
                "following_count": stats.get("followingCount", 0),
                "heart_count": stats.get("heartCount", 0),
                "video_count": stats.get("videoCount", 0),
            }

        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to parse TikTok profile: %s", exc)
            return None

    async def process(
        self,
        url: str,
        context: str,
        original_url: str,
    ) -> Optional[MediaResult]:
        """Извлекает данные профиля и возвращает typed `MediaResult`."""
        await self._media_gateway.random_delay()

        profile_info = await self._extract_profile_info(url)
        if not profile_info:
            return None

        avatar_path = None
        avatar_url = profile_info.get("avatar_url")
        if isinstance(avatar_url, str) and avatar_url:
            avatar_path = self._media_gateway.generate_unique_path(
                profile_info.get("unique_id") or "avatar",
                suffix=".jpg",
            )
            if not await self._media_gateway.download_photo(
                avatar_url,
                avatar_path,
                size_limit=self._media_gateway.photo_limit,
            ):
                avatar_path = None

        unique_id = profile_info.get("unique_id")
        profile_link = f"https://www.tiktok.com/@{unique_id}" if unique_id else url

        lines: list[str] = []
        nickname = profile_info.get("nickname")
        if nickname:
            lines.append(f'<a href="{profile_link}"><b>{nickname}</b></a>')
        elif unique_id:
            lines.append(f'<a href="{profile_link}"><b>@{unique_id}</b></a>')
        else:
            lines.append(f'<a href="{profile_link}"><b>TikTok Profile</b></a>')

        signature = profile_info.get("signature")
        if isinstance(signature, str) and signature:
            if len(signature) > 200:
                signature = signature[:200] + "…"
            lines.append(f"<i>{signature}</i>")

        lines.append("")
        lines.append(f"👥 Подписчиков: {profile_info.get('follower_count', 0):,}")
        lines.append(f"👤 Подписок: {profile_info.get('following_count', 0):,}")
        lines.append(f"❤️ Лайков: {profile_info.get('heart_count', 0):,}")
        lines.append(f"🎥 Видео: {profile_info.get('video_count', 0):,}")

        return MediaResult(
            content_type=ContentType.PROFILE,
            source_name="TikTok",
            original_url=original_url,
            context=context,
            main_file_path=avatar_path,
            thumbnail_path=None,
            title=nickname or unique_id or "unknown",
            uploader=unique_id or "unknown",
            caption_text="\n".join(lines),
        )