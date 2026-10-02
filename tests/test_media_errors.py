"""Download failures keep their cause and explain the failure to the user."""

import io
import logging
import re
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yt_dlp

from djgurda import media
from djgurda.diagnostics import DownloadLogger, diagnostic
from djgurda.sources import yandex_music

JOB = media.Job(media.CLOUD_MAX_BYTES, lambda duration: None)


@pytest.mark.parametrize(
    ("detail", "reason"),
    [
        ("Read timed out. (read timeout=30.0)", "источник не ответил вовремя"),
        ("Sign in to confirm you're not a bot", "требует авторизацию"),
        ("Video unavailable. This video has been removed", "видео недоступно"),
        ("Unexpected extractor failure", "не удалось скачать медиа с источника"),
    ],
)
def test_download_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, detail: str, reason: str
) -> None:
    failure = yt_dlp.utils.DownloadError(detail)
    downloader = MagicMock()
    downloader.__enter__.return_value.extract_info.side_effect = failure
    monkeypatch.setattr(yt_dlp, "YoutubeDL", lambda options: downloader)
    with pytest.raises(media.MediaError, match=reason) as raised:
        media.download("https://example.com/video", tmp_path, JOB)
    assert raised.value.__cause__ is failure
    assert detail in diagnostic(raised.value)


def test_diagnostics_redact_credentials(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("YANDEX_MUSIC_TOKEN", "test-secret-music")
    detail = (
        "Failed: test-secret-music 123456789:test-secret-bot "
        "https://example.com/video?signature=test-signed-url"
    )
    logger = DownloadLogger(logging.getLogger("test.download"))
    logger.error(detail)
    output = caplog.text + diagnostic(RuntimeError(detail))
    assert "Failed:" in output
    assert "RuntimeError" in output
    assert "test-secret" not in output
    assert "test-signed-url" not in output


def test_missing_download_is_not_reported_as_oversized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    downloader = MagicMock()
    downloader.__enter__.return_value.extract_info.return_value = {}
    downloader.__enter__.return_value.process_ie_result.return_value = {}
    monkeypatch.setattr(yt_dlp, "YoutubeDL", lambda options: downloader)
    with pytest.raises(media.MediaError, match="не предоставил файл"):
        media.download("https://example.com/video", tmp_path, JOB)


@pytest.mark.parametrize(
    ("deadline", "size", "reason"),
    [
        (-1, 10, "загрузка не уложилась в 2 мин"),
        (60, yandex_music.MAX_BYTES + 1, "файл больше 50 МБ"),
    ],
)
def test_yandex_music_download_is_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, deadline: float, size: int, reason: str
) -> None:
    monkeypatch.setattr(yandex_music, "urlopen", lambda url, timeout: io.BytesIO(b"x" * size))
    with pytest.raises(media.MediaError, match=reason):
        yandex_music.save(
            "https://example.com/track", tmp_path / "track.mp3", deadline + time.monotonic()
        )


class Selected(Exception):
    """Stops a test download once yt-dlp has chosen its formats."""


@pytest.mark.parametrize(
    ("max_mb", "expected"),
    [
        (50, "480+audio"),  # 720p H.264 exceeds 50 MB: the best H.264 that fits.
        (5, None),  # Even 360p does not fit.
    ],
)
def test_too_big_quality_falls_back_to_one_that_fits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, max_mb: int, expected: str | None
) -> None:
    def video(height: int, mb: int) -> dict[str, object]:
        return {
            "format_id": str(height),
            "url": f"https://example.com/{height}",
            "ext": "mp4",
            "protocol": "https",
            "vcodec": "avc1",
            "acodec": "none",
            "height": height,
            "width": height * 16 // 9,
            "filesize": mb * 1024 * 1024,
        }

    audio = {**video(0, 2), "format_id": "audio", "ext": "m4a", "vcodec": "none", "acodec": "mp4a"}
    info = {
        "id": "x",
        "title": "Title",
        "extractor": "generic",
        "extractor_key": "Generic",
        "webpage_url": "https://example.com/x",
        "duration": 60,
        "formats": [
            audio,
            video(360, 5),
            video(480, 20),
            video(720, 60),
            # HLS states no size, and yt-dlp does not estimate manifest formats; the bitrate
            # means 75 MB for the minute, so it does not fit either.
            {
                **video(720, 0),
                "format_id": "720hls",
                "filesize": None,
                "tbr": 10_000,
                "manifest_url": "https://example.com/720.m3u8",
            },
            # Fits, but H.264 is preferred even at a lower resolution.
            {**video(720, 30), "format_id": "720vp9", "vcodec": "vp9"},
            video(1080, 200),
        ],
    }
    process = yt_dlp.YoutubeDL.process_ie_result

    def select(ydl: yt_dlp.YoutubeDL, item: dict[str, object], download: bool = True) -> object:
        chosen = process(ydl, item, download=False)  # Real yt-dlp format selection, no network.
        if download:
            raise Selected(chosen["format_id"])
        return chosen

    monkeypatch.setattr(
        yt_dlp.YoutubeDL, "extract_info", lambda ydl, url, download: select(ydl, dict(info), False)
    )
    monkeypatch.setattr(yt_dlp.YoutubeDL, "process_ie_result", select)
    job = media.Job(max_mb * 1024 * 1024, lambda duration: None)
    if expected is None:
        with pytest.raises(media.MediaError, match=f"файл больше {max_mb} МБ"):
            media.download("https://example.com/x", tmp_path, job)
    else:
        with pytest.raises(Selected, match=re.escape(expected)):
            media.download("https://example.com/x", tmp_path, job)
