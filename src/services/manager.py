# src/services/manager.py
import re
from typing import List, Optional

from src.services.base import BaseHandler
from src.services.YouTube import YouTubeShortsHandler
from src.services.YandexMusic import YandexMusicHandler
from src.services.TikTok import TikTokHandler
from src.services.Instagram import InstagramReelsHandler


class ServiceManager:
    def __init__(self):
        self.handlers: List[BaseHandler] = [
            YouTubeShortsHandler(),
            YandexMusicHandler(),
            TikTokHandler(),
            InstagramReelsHandler(),
        ]

    def get_handler(self, url: str) -> Optional[BaseHandler]:
        for handler in self.handlers:
            if handler.pattern.search(url):
                return handler
        return None