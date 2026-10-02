"""Instagram: Reels are downloaded through a mirror; posts, stories and profiles are classified."""

from pathlib import Path
from urllib.parse import SplitResult, urlsplit

from djgurda.media import Job, Media, download
from djgurda.sources.base import Source

# Serves the reel file to link-preview bots without an Instagram login.
MIRROR = "www.kkinstagram.com"
MIRROR_HEADERS = {"User-Agent": "TelegramBot (like TwitterBot)"}


def parts(url: SplitResult) -> list[str]:
    return [part for part in url.path.split("/") if part]


def kind(url: SplitResult) -> str | None:
    path = parts(url)
    if len(path) > 1 and path[0] in ("reel", "reels"):
        return "reel"
    if len(path) > 1 and path[0] == "p":
        return "post"
    if len(path) > 2 and path[0] == "stories":
        return "stories"
    return None


def media_id(url: SplitResult) -> str | None:
    path = parts(url)
    return path[1] if kind(url) in ("reel", "post") else None


def fetch(url: str, target: Path, job: Job) -> Media:
    shortcode = parts(urlsplit(url))[1]
    return download(f"https://{MIRROR}/reel/{shortcode}/", target, job, MIRROR_HEADERS)


INSTAGRAM = Source(
    "Instagram",
    ("instagram.com",),
    kind,
    frozenset({"reel"}),
    media_id,
    aliases=(
        ("kkinstagram.com", "instagram.com"),
        ("ddinstagram.com", "instagram.com"),
        ("instagramez.com", "instagram.com"),
        ("eeinstagram.com", "instagram.com"),
    ),
    tracking=frozenset({"igsh", "igshid", "stkn"}),
    fetch=fetch,
)
