"""Instagram: Reels are downloaded through a mirror; posts, stories and profiles are classified."""

import logging
from dataclasses import replace
from pathlib import Path
from urllib.parse import SplitResult, urlsplit

import yt_dlp

from djgurda.diagnostics import DownloadLogger, redact
from djgurda.media import Admit, Media, download
from djgurda.sources.base import Source

# Serves the reel file to link-preview bots without an Instagram login.
MIRROR = "www.kkinstagram.com"
MIRROR_HEADERS = {"User-Agent": "TelegramBot (like TwitterBot)"}

logger = logging.getLogger(__name__)


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


def describe(url: str) -> tuple[str, str]:
    """Best-effort title and author; Instagram often requires a login for this."""
    options = {
        "quiet": True,
        "no_warnings": True,
        "cachedir": False,
        "socket_timeout": 15,
        "logger": DownloadLogger(logger),
    }
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as error:
        logger.info("No Instagram metadata: %s", redact(str(error)))
        return "", ""
    text = (info.get("description") or "").split("\n", 1)[0]
    return text, info.get("channel") or info.get("uploader") or ""


def fetch(url: str, target: Path, admit: Admit) -> Media:
    shortcode = parts(urlsplit(url))[1]
    media = download(f"https://{MIRROR}/reel/{shortcode}/", target, admit, MIRROR_HEADERS)
    title, author = describe(url)
    return replace(media, info=replace(media.info, title=title, uploader=author))


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
