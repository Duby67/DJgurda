from typing import List, Optional

from src.services.base import BaseHandler
from src.services.TikTok import TikTokHandler
from src.services.YouTube import YouTubeHandler
from src.services.Instagram import InstagramHandler
from src.services.YandexMusic import YandexMusicHandler

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