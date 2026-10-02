"""Yandex Music: tracks are downloaded as audio; albums, artists and playlists are classified."""

import logging
import time
from pathlib import Path
from urllib.parse import SplitResult, urlsplit
from urllib.request import urlopen

from yandex_music import Client
from yandex_music.exceptions import YandexMusicError

from djgurda.media import LONG_DURATION, Info, Job, Media, MediaError, megabytes, thumbnail
from djgurda.sources.base import Source

# Tracks keep the short lane and a small cap.
MAX_BYTES = 50 * 1024 * 1024
MAX_DURATION = LONG_DURATION
DOWNLOAD_TIMEOUT = 2 * 60  # Seconds for one track, API calls included.
SOCKET_TIMEOUT = 30
CHUNK = 64 * 1024

logger = logging.getLogger(__name__)
token: str | None = None  # Set at startup; downloads need an account with a subscription.
client: Client | None = None


def configure(value: str | None) -> None:
    global token, client
    token, client = value, None


def parts(url: SplitResult) -> list[str]:
    return [part for part in url.path.split("/") if part]


def kind(url: SplitResult) -> str | None:
    path = parts(url)
    if "track" in path[:-1]:
        return "track"
    if len(path) > 1 and path[0] in ("album", "artist"):
        return path[0]
    if "playlists" in path[:-1]:
        return "playlist"
    return None


def media_id(url: SplitResult) -> str | None:
    path = parts(url)
    return path[path.index("track") + 1] if kind(url) == "track" else None


def save(url: str, path: Path, deadline: float) -> None:
    """Stream the file to disk, stopping at the deadline or the size cap.

    The client's own download has only a per-read timeout and keeps the file in memory.
    """
    try:
        with urlopen(url, timeout=SOCKET_TIMEOUT) as response, path.open("wb") as file:
            size = 0
            while chunk := response.read(CHUNK):
                check(deadline)
                size += len(chunk)
                if size > MAX_BYTES:
                    raise MediaError(f"файл больше {megabytes(MAX_BYTES)}")
                file.write(chunk)
    except OSError as error:
        raise MediaError("не удалось скачать") from error


def check(deadline: float) -> None:
    if time.monotonic() > deadline:
        raise MediaError(f"загрузка не уложилась в {DOWNLOAD_TIMEOUT // 60} мин")


def fetch(url: str, target: Path, job: Job) -> Media:
    global client
    deadline = time.monotonic() + DOWNLOAD_TIMEOUT
    if not token:
        logger.error("YANDEX_MUSIC_TOKEN is not set; Yandex Music links cannot be downloaded")
        raise MediaError("Яндекс Музыка не подключена")
    track_id = media_id(urlsplit(url))
    try:
        client = client or Client(token).init()
        tracks = client.tracks([track_id])
        if not tracks:
            raise MediaError("трек не найден")
        track = tracks[0]
        if (track.duration_ms or 0) > MAX_DURATION * 1000:
            raise MediaError(f"трек длиннее {MAX_DURATION // 60} минут")
        job.admit((track.duration_ms or 0) // 1000 or None)
        best = max(track.get_download_info(), key=lambda item: item.bitrate_in_kbps or 0)
        path = target / f"track.{'m4a' if best.codec == 'aac' else best.codec}"
        job.stage = "скачивание"
        check(deadline)
        save(best.get_direct_link(), path, deadline)
        cover = None
        if track.cover_uri:
            check(deadline)
            cover = target / "cover.jpg"
            track.download_cover(str(cover), size="400x400")
    except YandexMusicError as error:
        raise MediaError("не удалось скачать") from error
    info = Info(
        title=track.title or "",
        uploader=", ".join(artist.name for artist in track.artists or [] if artist.name),
        duration=(track.duration_ms or 0) // 1000 or None,
        width=None,
        height=None,
    )
    return Media(path, info, cover, thumbnail(cover) if cover else None)


YANDEX_MUSIC = Source(
    "Yandex Music",
    ("music.yandex.ru", "music.yandex.com", "music.yandex.by", "music.yandex.kz"),
    kind,
    frozenset({"track"}),
    media_id,
    audio=frozenset({"track"}),
    fetch=fetch,
)
