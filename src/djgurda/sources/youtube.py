"""YouTube: videos and Shorts are downloaded; playlists and channels are only classified."""

from urllib.parse import SplitResult, parse_qs

from djgurda.sources.base import Source


def kind(url: SplitResult) -> str | None:
    parts = [part for part in url.path.split("/") if part]
    if not parts:
        return None
    if (url.hostname or "").endswith("youtu.be"):
        return "video"
    first = parts[0]
    if first == "watch":
        return "video" if parse_qs(url.query).get("v") else None
    if first in ("live", "embed", "v") and len(parts) > 1:
        return "video"
    if first == "shorts" and len(parts) > 1:
        return "shorts"
    if first == "playlist":
        return "playlist"
    if first.startswith("@") or first in ("channel", "c", "user"):
        return "channel"
    return None


YOUTUBE = Source("YouTube", ("youtube.com", "youtu.be"), kind, frozenset({"video", "shorts"}))
