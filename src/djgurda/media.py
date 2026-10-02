"""Media download shared by all sources."""

import logging
import re
import shutil
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import yt_dlp

from djgurda.diagnostics import DownloadLogger

LOCAL_MAX_BYTES = 2000 * 1024 * 1024  # The local Bot API upload limit.
CLOUD_MAX_BYTES = 50 * 1024 * 1024  # Cloud Bot API upload limit.
# Preferred ceiling for the smaller side (vertical Shorts get 480p too); when a source has
# nothing that small, yt-dlp picks its smallest variant instead.
MAX_RESOLUTION = 480
MAX_DURATION = 2 * 60 * 60  # Seconds; HLS sizes are often unknown, so length is the cheap guard.
LONG_DURATION = 20 * 60  # Longer media moves to its own lane so short links keep flowing.
DOWNLOAD_TIMEOUT = 5 * 60  # Seconds for download and merge of one link.
LONG_DOWNLOAD_TIMEOUT = 60 * 60
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


def megabytes(size: int) -> str:
    return f"{size // (1024 * 1024)} МБ"


@dataclass
class Job:
    """One link's download, shared by the chat and the download thread."""

    max_bytes: int
    # Called from the download thread with the media duration before the transfer starts;
    # raises MediaError when the media has no free lane.
    admit: Callable[[int | None], None]
    stage: str = "в очереди"  # Shown to the user; written by the download thread.
    long: bool = False  # Admitted to the long lane; its upload gets more time.


def require_space(target: Path, size: int, job: Job) -> None:
    """Merging keeps both streams and the result on disk at once."""
    free = shutil.disk_usage(target).free
    if free < 2 * (size or job.max_bytes):
        logger.error("Not enough disk space: %s free for %s", free, size or "unknown size")
        raise MediaError("на сервере недостаточно места для загрузки")


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


def download(url: str, target: Path, job: Job, headers: dict[str, str] | None = None) -> Media:
    limit = DOWNLOAD_TIMEOUT
    deadline = time.monotonic() + limit

    def on_download(progress: dict[str, Any]) -> None:
        if time.monotonic() > deadline:
            raise Timeout()
        if progress["status"] == "downloading":  # Streams are reported one after another.
            done = progress.get("downloaded_bytes") or 0
            total = progress.get("total_bytes") or progress.get("total_bytes_estimate")
            job.stage = (
                f"скачивание {min(99, done * 100 // total)}%"
                if total
                else (f"скачивание, {megabytes(done)}")
            )

    def on_process(progress: dict[str, Any]) -> None:
        if time.monotonic() > deadline:
            raise Timeout()
        if progress["status"] == "started":
            job.stage = "обработка"

    options: dict[str, Any] = {
        "paths": {"home": str(target), "temp": str(target)},
        "outtmpl": "media.%(ext)s",  # One download per directory; ids can be URLs.
        "format": "bv*+ba/b",
        "format_sort": [f"res:{MAX_RESOLUTION}", "vcodec:h264", "ext:mp4:m4a"],
        "merge_output_format": "mp4",
        "max_filesize": job.max_bytes,
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
        "progress_hooks": [on_download],
        "postprocessor_hooks": [on_process],
    }
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
            if info.get("is_live"):
                raise MediaError("прямые трансляции не поддерживаются")
            duration = info.get("duration") or 0
            if duration > MAX_DURATION:
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
            if size > job.max_bytes:
                raise MediaError(f"файл больше {megabytes(job.max_bytes)}")
            require_space(target, int(size), job)
            job.admit(duration or None)
            if duration > LONG_DURATION:
                limit = LONG_DOWNLOAD_TIMEOUT
                deadline = time.monotonic() + limit
            info = ydl.process_ie_result(info, download=True)
    except Timeout as error:
        raise MediaError(f"загрузка дольше {limit // 60} минут") from error
    except yt_dlp.utils.DownloadError as error:
        raise MediaError(download_reason(error)) from error
    downloads = info.get("requested_downloads") or []
    path = Path(downloads[0]["filepath"]) if downloads else None
    if path is None or not path.is_file():
        raise MediaError("источник не предоставил файл для скачивания")
    if path.stat().st_size > job.max_bytes:
        raise MediaError(f"файл больше {megabytes(job.max_bytes)}")
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
