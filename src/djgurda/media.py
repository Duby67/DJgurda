"""Media download shared by all sources."""

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yt_dlp

MAX_BYTES = 50 * 1024 * 1024  # Bot API upload limit.
MAX_RESOLUTION = 480  # Smaller side, so vertical Shorts get 480p as well.
DOWNLOAD_PREFIX = "download-"


class MediaError(Exception):
    """A user-facing reason why a link produced no media."""


@dataclass(frozen=True)
class Media:
    path: Path
    title: str
    uploader: str
    duration: int | None
    width: int | None
    height: int | None


def prepare_work_dir(work_dir: Path) -> None:
    """Create the download root and remove directories left by an interrupted run."""
    work_dir.mkdir(parents=True, exist_ok=True)
    for leftover in work_dir.glob(DOWNLOAD_PREFIX + "*"):
        shutil.rmtree(leftover)


def download(url: str, target: Path) -> Media:
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
    }
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
            if info.get("is_live"):
                raise MediaError("прямые трансляции не поддерживаются")
            formats = info.get("requested_formats") or [info]
            if any(
                min(item.get("width") or 0, item.get("height") or 0) > MAX_RESOLUTION
                for item in formats
            ):
                raise MediaError(f"нет качества {MAX_RESOLUTION}p или ниже")
            size = sum(item.get("filesize") or item.get("filesize_approx") or 0 for item in formats)
            if size > MAX_BYTES:
                raise MediaError("файл больше 50 МБ")
            info = ydl.process_ie_result(info, download=True)
    except yt_dlp.utils.DownloadError as error:
        raise MediaError("не удалось скачать") from error
    downloads = info.get("requested_downloads") or []
    path = Path(downloads[0]["filepath"]) if downloads else None
    if path is None or not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise MediaError("файл больше 50 МБ")
    return Media(
        path=path,
        title=info.get("title") or "",
        uploader=info.get("channel") or info.get("uploader") or "",
        duration=int(info["duration"]) if info.get("duration") else None,
        width=info.get("width"),
        height=info.get("height"),
    )
