"""Link extraction and source classification."""

from dataclasses import dataclass
from urllib.parse import urlsplit

from aiogram.types import Message


@dataclass(frozen=True)
class Source:
    name: str
    domains: tuple[str, ...]

    def matches(self, host: str) -> bool:
        return any(host == domain or host.endswith("." + domain) for domain in self.domains)


SOURCES = (
    Source("YouTube", ("youtube.com", "youtu.be")),
    Source("TikTok", ("tiktok.com",)),
    Source("Instagram", ("instagram.com",)),
    Source("VK", ("vk.com", "vk.ru", "vkvideo.ru")),
    Source("Coub", ("coub.com",)),
    Source("Yandex Music", ("music.yandex.ru", "music.yandex.com")),
)


def extract_links(message: Message) -> list[str]:
    text = message.text or message.caption or ""
    entities = message.entities or message.caption_entities or []
    links = []
    for entity in entities:
        if entity.type == "url":
            links.append(entity.extract_from(text))
        elif entity.type == "text_link" and entity.url:
            links.append(entity.url)
    return links


def classify(url: str) -> Source | None:
    if "://" not in url:
        url = "https://" + url
    try:
        host = urlsplit(url).hostname or ""
    except ValueError:
        return None
    return next((source for source in SOURCES if source.matches(host)), None)
