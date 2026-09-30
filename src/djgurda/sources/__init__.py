"""Source registry and link classification."""

from urllib.parse import urlsplit

from djgurda.sources.base import Link, Source
from djgurda.sources.youtube import YOUTUBE

SOURCES = (
    YOUTUBE,
    Source("TikTok", ("tiktok.com",)),
    Source("Instagram", ("instagram.com",)),
    Source("VK", ("vk.com", "vk.ru", "vkvideo.ru")),
    Source("Coub", ("coub.com",)),
    Source("Yandex Music", ("music.yandex.ru", "music.yandex.com")),
)


def classify(url: str) -> Link | None:
    if "://" not in url:
        url = "https://" + url
    try:
        parts = urlsplit(url)
        host = parts.hostname or ""
    except ValueError:
        return None
    source = next((source for source in SOURCES if source.matches(host)), None)
    return Link(url, source, source.kind(parts)) if source else None
