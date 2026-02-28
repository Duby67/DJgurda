from typing import List, Optional

from src.handlers.base import BaseHandler
from src.handlers.TikTok import TikTokHandler
from src.handlers.YouTube import YouTubeHandler
from src.handlers.Instagram import InstagramHandler
from src.handlers.YandexMusic import YandexMusicHandler

class ServiceManager:
    def __init__(self):
        self.handlers: List[BaseHandler] = [
            TikTokHandler(),
            YouTubeHandler(),
            InstagramHandler(),
            YandexMusicHandler(),
        ]

    def get_handler(self, url: str) -> Optional[BaseHandler]:
        for handler in self.handlers:
            if handler.pattern.search(url):
                return handler
        return None