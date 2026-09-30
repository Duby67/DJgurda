"""TikTok: videos are downloaded with yt-dlp; photos and profiles are only classified."""

from urllib.parse import SplitResult

from djgurda.sources.base import Source

SHORT_HOSTS = ("vm.tiktok.com", "vt.tiktok.com")


def parts(url: SplitResult) -> list[str]:
    return [part for part in url.path.split("/") if part]


def kind(url: SplitResult) -> str | None:
    path = parts(url)
    if url.hostname in SHORT_HOSTS or (path and path[0] == "t"):
        return "video" if path else None  # Share links; yt-dlp follows the redirect.
    if len(path) > 2 and path[0].startswith("@") and path[1] in ("video", "photo"):
        return path[1]
    if len(path) == 1 and path[0].startswith("@"):
        return "profile"
    return None


def media_id(url: SplitResult) -> str | None:
    path = parts(url)
    if url.hostname in SHORT_HOSTS and path:
        return path[0]
    if len(path) > 1 and path[0] == "t":
        return path[1]
    return path[2] if kind(url) in ("video", "photo") else None


TIKTOK = Source(
    "TikTok",
    ("tiktok.com",),
    kind,
    frozenset({"video"}),
    media_id,
    aliases=(
        ("vxtiktok.com", "tiktok.com"),
        ("tnktok.com", "tiktok.com"),
        ("tiktxk.com", "tiktok.com"),
    ),
    tracking=frozenset({"_r", "_t", "is_from_webapp", "sender_device", "web_id"}),
)
