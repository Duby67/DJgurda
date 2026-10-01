"""Media download shared by all sources."""

import logging
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import yt_dlp

from djgurda.diagnostics import DownloadLogger

MAX_BYTES = 50 * 1024 * 1024  # Bot API upload limit.
# Preferred ceiling for the smaller side (vertical Shorts get 480p too); when a source has
# nothing that small, yt-dlp picks its smallest variant instead.
MAX_RESOLUTION = 480
MAX_DURATION = 20 * 60  # Seconds; HLS sizes are often unknown, so length is the cheap guard.
DOWNLOAD_TIMEOUT = 5 * 60  # Seconds for download and merge of one link.
DOWNLOAD_PREFIX = "download-"
THUMBNAIL_SIZE = 320  # Bot API limit for video thumbnails.
DURATION = re.compile(r"Duration: (\d+):(\d+):(\d+)")
SIZE = re.compile(r"Video: .*?, (\d{2,5})x(\d{2,5})")

logger = logging.getLogger(__name__)


class MediaError(Exception):
    """A user-facing reason why a link produced no media."""


def download_reason(error: Exception) -> str:
    reason = str(error).lower()
    if any(word in reason for word in ("timed out", "timeout")):
        return "источник не ответил вовремя, попробуйте позже"
    if any(word in reason for word in ("sign in", "log in", "login", "cookies", "private video")):
        return "источник требует авторизацию; бот не может скачать это видео"
    if any(
        word in reason
        for word in (
            "video unavailable",
            "video is not available",
            "has been removed",
            "http error 404",
        )
    ):
        return "видео недоступно: удалено или ограничено источником"
    return "не удалось скачать медиа с источника, попробуйте позже"


class Timeout(yt_dlp.utils.DownloadCancelled):  # type: ignore[misc]  # yt-dlp is untyped.
    msg = "Download timed out"


@dataclass(frozen=True)
class Info:
    title: str
    uploader: str
    duration: int | None
    width: int | None
    height: int | None


@dataclass(frozen=True)
class Media:
    path: Path
    info: Info
    cover: Path | None = None  # Author's preview image shown before playback.
    thumbnail: Path | None = None


def prepare_work_dir(work_dir: Path) -> None:
    """Create the download root and remove directories left by an interrupted run."""
    work_dir.mkdir(parents=True, exist_ok=True)
    for leftover in work_dir.glob(DOWNLOAD_PREFIX + "*"):
        shutil.rmtree(leftover)


def download(url: str, target: Path, headers: dict[str, str] | None = None) -> Media:
    deadline = time.monotonic() + DOWNLOAD_TIMEOUT

    def check_deadline(progress: dict[str, Any]) -> None:
        if time.monotonic() > deadline:
            raise Timeout()

    options: dict[str, Any] = {
        "paths": {"home": str(target), "temp": str(target)},
        "outtmpl": "media.%(ext)s",  # One download per directory; ids can be URLs.
        "format": "bv*+ba/b",
        "format_sort": [f"res:{MAX_RESOLUTION}", "vcodec:h264", "ext:mp4:m4a"],
        "merge_output_format": "mp4",
        "max_filesize": MAX_BYTES,
        "noplaylist": True,
        "cachedir": False,
        "socket_timeout": 30,
        "quiet": True,
        "logger": DownloadLogger(logger),
        "no_warnings": True,
        "noprogress": True,
        "writethumbnail": True,
        "postprocessors": [
            {"key": "FFmpegThumbnailsConvertor", "format": "jpg", "when": "before_dl"}
        ],
        "http_headers": headers or {},
        "progress_hooks": [check_deadline],
        "postprocessor_hooks": [check_deadline],
    }
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
            if info.get("is_live"):
                raise MediaError("прямые трансляции не поддерживаются")
            if (info.get("duration") or 0) > MAX_DURATION:
                raise MediaError(f"видео длиннее {MAX_DURATION // 60} минут")
            formats = info.get("requested_formats") or [info]
            if info.get("section_start") is not None:
                # Clips: format sizes describe the whole video, so estimate from bitrate (kbit/s).
                bitrate = sum(item.get("tbr") or 0 for item in formats)
                size = bitrate * 125 * (info.get("duration") or 0)
            else:
                size = sum(
                    item.get("filesize") or item.get("filesize_approx") or 0 for item in formats
                )
            if size > MAX_BYTES:
                raise MediaError("файл больше 50 МБ")
            info = ydl.process_ie_result(info, download=True)
    except Timeout as error:
        raise MediaError(f"загрузка дольше {DOWNLOAD_TIMEOUT // 60} минут") from error
    except yt_dlp.utils.DownloadError as error:
        raise MediaError(download_reason(error)) from error
    downloads = info.get("requested_downloads") or []
    path = Path(downloads[0]["filepath"]) if downloads else None
    if path is None or not path.is_file():
        raise MediaError("источник не предоставил файл для скачивания")
    if path.stat().st_size > MAX_BYTES:
        raise MediaError("файл больше 50 МБ")
    details = info_of(info)
    if not (details.duration and details.width and details.height):
        details = probe(path, details)  # Direct files carry no metadata in yt-dlp.
    cover = next(target.glob("*.jpg"), None)
    if cover is None:
        logger.info("No preview image for %s; Telegram will use the first frame", url)
        return Media(path, details)
    return Media(path, details, cover, thumbnail(cover))


def probe(path: Path, info: Info) -> Info:
    """Fill duration and size from the file header using ffmpeg."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-i", str(path)], capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError) as error:
        logger.warning("Cannot probe %s: %s", path, error)
        return info
    duration = DURATION.search(result.stderr)
    size = SIZE.search(result.stderr)
    return replace(
        info,
        duration=info.duration
        or (
            int(duration[1]) * 3600 + int(duration[2]) * 60 + int(duration[3]) if duration else None
        ),
        width=info.width or (int(size[1]) if size else None),
        height=info.height or (int(size[2]) if size else None),
    )


def thumbnail(cover: Path) -> Path | None:
    small = cover.with_name("thumbnail.jpg")
    size = THUMBNAIL_SIZE
    command = ["ffmpeg", "-v", "error", "-y", "-i", str(cover), "-q:v", "5"]
    command += ["-vf", f"scale={size}:{size}:force_original_aspect_ratio=decrease", str(small)]
    try:
        subprocess.run(command, check=True, capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as error:
        logger.warning("Cannot make a thumbnail from %s: %s", cover, error)
        return None
    return small


def info_of(info: dict[str, Any]) -> Info:
    return Info(
        title=info.get("title") or "",
        uploader=info.get("channel") or info.get("uploader") or "",
        duration=int(info["duration"]) if info.get("duration") else None,
        width=info.get("width"),
        height=info.get("height"),
    )
