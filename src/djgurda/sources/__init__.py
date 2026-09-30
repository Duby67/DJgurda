"""Source registry and link classification."""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from djgurda.sources.base import Link, Source
from djgurda.sources.instagram import INSTAGRAM
from djgurda.sources.tiktok import TIKTOK
from djgurda.sources.yandex_music import YANDEX_MUSIC
from djgurda.sources.youtube import YOUTUBE

SOURCES = (
    YOUTUBE,
    TIKTOK,
    INSTAGRAM,
    Source("VK", ("vk.com", "vk.ru", "vkvideo.ru")),
    Source("Coub", ("coub.com",)),
    YANDEX_MUSIC,
)


def classify(url: str) -> Link | None:
    """Recognize a link, including mirror domains, and return it in canonical form."""
    if "://" not in url:
        url = "https://" + url
    try:
        parts = urlsplit(url)
        host = parts.hostname or ""
    except ValueError:
        return None
    for source in SOURCES:
        canonical = source.canonical_host(host)
        if canonical:
            break
    else:
        return None
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key not in source.tracking and not key.startswith("utm_")
    ]
    parts = parts._replace(scheme="https", netloc=canonical, query=urlencode(query))
    return Link(
        urlunsplit(parts),
        source,
        source.kind(parts),
        source.media_id(parts),
        source.start(parts),
    )
