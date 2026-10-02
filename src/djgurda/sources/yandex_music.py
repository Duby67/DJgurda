"""Yandex Music: tracks are downloaded as audio; albums, artists and playlists are classified."""

import logging
from pathlib import Path
from urllib.parse import SplitResult, urlsplit

from yandex_music import Client
from yandex_music.exceptions import YandexMusicError

from djgurda.media import LONG_DURATION, Admit, Info, Media, MediaError, megabytes, thumbnail
from djgurda.sources.base import Source

# The client reads the whole file into memory, so tracks keep the short lane and a small cap.
MAX_BYTES = 50 * 1024 * 1024
MAX_DURATION = LONG_DURATION

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


def fetch(url: str, target: Path, admit: Admit) -> Media:
    global client
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
        admit((track.duration_ms or 0) // 1000 or None)
        best = max(track.get_download_info(), key=lambda item: item.bitrate_in_kbps or 0)
        path = target / f"track.{'m4a' if best.codec == 'aac' else best.codec}"
        track.download(str(path), codec=best.codec, bitrate_in_kbps=best.bitrate_in_kbps)
        cover = None
        if track.cover_uri:
            cover = target / "cover.jpg"
            track.download_cover(str(cover), size="400x400")
    except YandexMusicError as error:
        raise MediaError("не удалось скачать") from error
    if path.stat().st_size > MAX_BYTES:
        raise MediaError(f"файл больше {megabytes(MAX_BYTES)}")
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
