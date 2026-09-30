"""Media download shared by all sources."""

import logging
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yt_dlp

MAX_BYTES = 50 * 1024 * 1024  # Bot API upload limit.
MAX_RESOLUTION = 480  # Smaller side, so vertical Shorts get 480p as well.
MAX_DURATION = 20 * 60  # Seconds; HLS sizes are often unknown, so length is the cheap guard.
DOWNLOAD_TIMEOUT = 5 * 60  # Seconds for download and merge of one link.
DOWNLOAD_PREFIX = "download-"
THUMBNAIL_SIZE = 320  # Bot API limit for video thumbnails.

logger = logging.getLogger(__name__)


class MediaError(Exception):
    """A user-facing reason why a link produced no media."""


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


def download(url: str, target: Path) -> Media:
    deadline = time.monotonic() + DOWNLOAD_TIMEOUT

    def check_deadline(progress: dict[str, Any]) -> None:
        if time.monotonic() > deadline:
            raise Timeout()

    options: dict[str, Any] = {
        "paths": {"home": str(target), "temp": str(target)},
        "outtmpl": "%(id)s.%(ext)s",
        "format": "bv*+ba/b",
        "format_sort": [f"res:{MAX_RESOLUTION}", "vcodec:h264", "ext:mp4:m4a"],
        "merge_output_format": "mp4",
        "max_filesize": MAX_BYTES,
        "noplaylist": True,
        "cachedir": False,
        "socket_timeout": 30,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "writethumbnail": True,
        "postprocessors": [
            {"key": "FFmpegThumbnailsConvertor", "format": "jpg", "when": "before_dl"}
        ],
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
            if any(
                min(item.get("width") or 0, item.get("height") or 0) > MAX_RESOLUTION
                for item in formats
            ):
                raise MediaError(f"нет качества {MAX_RESOLUTION}p или ниже")
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
        raise MediaError("не удалось скачать") from error
    downloads = info.get("requested_downloads") or []
    path = Path(downloads[0]["filepath"]) if downloads else None
    if path is None or not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise MediaError("файл больше 50 МБ")
    cover = next(target.glob("*.jpg"), None)
    if cover is None:
        logger.warning("No preview image for %s; Telegram will use the first frame", url)
        return Media(path, info_of(info))
    return Media(path, info_of(info), cover, thumbnail(cover))


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
