"""Download failures keep their cause and explain the failure to the user."""

import io
import logging
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
