"""Unit-тесты sender registry для media_group presentation."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any

# test/bot/processing/test_sender_registry.py -> project root это parents[3]
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("BOT_DB_PATH", str(PROJECT_ROOT / "src" / "data" / "db" / "bot.db"))
os.environ.setdefault("BOT_VERSION", "local-test")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("BOT_TOKEN", "local-test-token")
os.environ.setdefault("YANDEX_MUSIC_TOKEN", "local-test-token")
os.environ.setdefault("YOUTUBE_COOKIES_ENABLED", "false")

from src.bot.processing.senders.registry import _send_media_group, _send_profile_or_channel
from src.handlers.contracts import AttachmentKind, AudioAttachment, ContentType, MediaAttachment, MediaResult


class FakeMessage:
    """Минимальная модель aiogram Message для sender unit-тестов."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def answer(self, text: str) -> None:
        self.calls.append({"kind": "text", "text": text})

    async def answer_audio(self, **kwargs: Any) -> None:
        self.calls.append({"kind": "audio", **kwargs})

    async def answer_photo(self, **kwargs: Any) -> None:
        self.calls.append({"kind": "photo", **kwargs})

    async def answer_video(self, **kwargs: Any) -> None:
        self.calls.append({"kind": "video", **kwargs})

    async def answer_media_group(self, media: list[Any]) -> None:
        self.calls.append(
            {
                "kind": "media_group",
                "count": len(media),
                "first_caption": getattr(media[0], "caption", None) if media else None,
            }
        )


def test_send_media_group_sends_lead_text_before_attachments(tmp_path: Path) -> None:
    """Lead-text должен уходить перед audio/photo payload."""
    photo_path = tmp_path / "photo.jpg"
    photo_path.write_bytes(b"photo")
    audio_path = tmp_path / "audio.m4a"
    audio_path.write_bytes(b"audio")

    result = MediaResult(
        content_type=ContentType.MEDIA_GROUP,
        source_name="VK",
        original_url="https://vk.com/wall1_2",
        context="ctx",
        title="Wall post",
        uploader="Author",
        lead_text="Long VK post text",
        media_group=(MediaAttachment(kind=AttachmentKind.PHOTO, file_path=photo_path),),
        audios=(AudioAttachment(file_path=audio_path, title="Track", performer="Artist"),),
    )
    message = FakeMessage()

    asyncio.run(_send_media_group(message, result, caption="standard caption"))

    assert [call["kind"] for call in message.calls] == ["text", "audio", "photo"]
    assert message.calls[0]["text"] == "Long VK post text"
    assert message.calls[2]["caption"] == "standard caption"


def test_send_media_group_keeps_standard_caption_for_audio_only_payload(tmp_path: Path) -> None:
    """Audio-only payload не должен терять стандартный caption после отправки аудио."""
    audio_path = tmp_path / "audio.m4a"
    audio_path.write_bytes(b"audio")

    result = MediaResult(
        content_type=ContentType.MEDIA_GROUP,
        source_name="VK",
        original_url="https://vk.com/wall1_3",
        context="ctx",
        title="Wall post",
        uploader="Author",
        lead_text="post text",
        audios=(AudioAttachment(file_path=audio_path, title="Track", performer="Artist"),),
    )
    message = FakeMessage()

    asyncio.run(_send_media_group(message, result, caption="standard caption"))

    assert [call["kind"] for call in message.calls] == ["text", "audio", "text"]
    assert message.calls[-1]["text"] == "standard caption"


def test_send_profile_or_channel_merges_standard_caption_into_single_photo_message(tmp_path: Path) -> None:
    """Profile card должен объединять rich-caption и стандартный caption в одно сообщение."""
    photo_path = tmp_path / "avatar.jpg"
    photo_path.write_bytes(b"avatar")

    result = MediaResult(
        content_type=ContentType.PROFILE,
        source_name="VK",
        original_url="https://vk.com/spaces",
        context="ctx",
        title="КОСМОС",
        uploader="spaces",
        caption_text="<a href=\"https://vk.com/spaces\"><b>КОСМОС</b></a>\n@spaces",
        main_file_path=photo_path,
    )
    message = FakeMessage()

    asyncio.run(_send_profile_or_channel(message, result, caption="standard caption"))

    assert [call["kind"] for call in message.calls] == ["photo"]
    assert message.calls[0]["caption"] == (
        "<a href=\"https://vk.com/spaces\"><b>КОСМОС</b></a>\n@spaces\n\nstandard caption"
    )
