"""YouTube: videos, Shorts and clips are downloaded; playlists and channels are only classified."""

import re
from urllib.parse import SplitResult, parse_qs

from djgurda.sources.base import Source

TIMESTAMP = re.compile(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s?)?")
VIDEO_PATHS = {"live": "video", "embed": "video", "v": "video", "shorts": "shorts", "clip": "clip"}


def parts(url: SplitResult) -> list[str]:
    return [part for part in url.path.split("/") if part]


def kind(url: SplitResult) -> str | None:
    path = parts(url)
    if not path:
        return None
    if (url.hostname or "").endswith("youtu.be"):
        return "video"
    first = path[0]
    if first == "watch":
        return "video" if parse_qs(url.query).get("v") else None
    if first in VIDEO_PATHS and len(path) > 1:
        return VIDEO_PATHS[first]
    if first == "playlist":
        return "playlist"
    if first.startswith("@") or first in ("channel", "c", "user"):
        return "channel"
    return None


def media_id(url: SplitResult) -> str | None:
    path = parts(url)
    if (url.hostname or "").endswith("youtu.be"):
        return path[0] if path else None
    if path == ["watch"]:
        return parse_qs(url.query).get("v", [None])[0]
    if len(path) > 1 and path[0] in VIDEO_PATHS:
        return path[1]
    return None


def start(url: SplitResult) -> int | None:
    """Parse `t=90`, `t=90s` or `t=1h2m3s` from the query or fragment."""
    value = (parse_qs(url.query).get("t") or parse_qs(url.fragment).get("t") or [""])[0]
    match = TIMESTAMP.fullmatch(value)
    if not value or not match:
        return None
    hours, minutes, seconds = (int(group or 0) for group in match.groups())
    return hours * 3600 + minutes * 60 + seconds or None


YOUTUBE = Source(
    "YouTube",
    ("youtube.com", "youtu.be"),
    kind,
    frozenset({"video", "shorts", "clip"}),
    media_id,
    start,
    aliases=(("youtube-nocookie.com", "youtube.com"), ("koutube.com", "youtube.com")),
    tracking=frozenset({"si", "feature", "pp"}),
)
