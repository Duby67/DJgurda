import re

from typing import Optional, Dict, Any

from .TikTokVideo import TikTokVideo
from .TikTokPhoto import TikTokPhoto
from .TikTokProfile import TikTokProfile
from src.handlers.base import BaseHandler

class TikTokHandler(
    BaseHandler, 
    TikTokVideo, 
    TikTokPhoto,
    TikTokProfile
    ):
    PATTERN = re.compile(
        r'https?://(?:www\.|m\.)?(?:tiktok\.com|vt\.tiktok\.com|vm\.tiktok\.com)\S+'
    )

    @property
    def pattern(self) -> re.Pattern:
        return self.PATTERN

    @property
    def source_name(self) -> str:
        return "TikTok"

    async def process(self, url: str, context: str, resolved_url: Optional[str] = None) -> Optional[Dict[str, Any]]:
        target_url = resolved_url or url
        if '/photo/' in target_url:
            return await self._process_tiktok_photo(target_url, context)
        elif '/video/' in target_url:
            return await self._process_tiktok_video(target_url, context)
        else:
            return await self._process_tiktok_profile(target_url, context)