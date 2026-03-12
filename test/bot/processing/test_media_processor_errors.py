"""Unit-тесты error-gate и текста причин в media_processor."""

from __future__ import annotations

import asyncio
import importlib
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

# test/bot/processing/test_media_processor_errors.py -> project root это parents[3]
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Минимальные env для загрузки src.config.
os.environ.setdefault("BOT_DB_PATH", str(PROJECT_ROOT / "src" / "data" / "db" / "bot.db"))
os.environ.setdefault("BOT_VERSION", "local-test")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("BOT_TOKEN", "local-test-token")
os.environ.setdefault("YANDEX_MUSIC_TOKEN", "local-test-token")
os.environ.setdefault("YOUTUBE_COOKIES_ENABLED", "false")

media_processor_module = importlib.import_module("src.bot.processing.media_processor")


class FakeMessage:
    """Минимальная модель aiogram Message для unit-теста process_block."""

    def __init__(self) -> None:
        self.chat = SimpleNamespace(id=500)
        self.from_user = SimpleNamespace(id=700, username="tester", full_name="Test User")
        self.message_id = 900
        self.answers: list[dict[str, Any]] = []

    async def answer(self, text: str, reply_parameters: Any = None) -> None:
        self.answers.append(
            {
                "text": text,
                "reply_parameters": reply_parameters,
            }
        )


class FakeHandler:
    """Фейковый handler, возвращающий `None` для ветки load-failed."""

    source_name = "FakeSource"

    async def process(self, *_args: Any, **_kwargs: Any) -> None:
        return None


def test_load_failed_error_not_sent_when_errors_disabled(monkeypatch: Any) -> None:
    """
    При `errors_enabled=False` сообщение об ошибке не отправляется.
    """
    message = FakeMessage()
    handler = FakeHandler()

    async def fake_errors_enabled(_chat_id: int) -> bool:
        return False

    monkeypatch.setattr(media_processor_module, "get_errors_enabled", fake_errors_enabled)

    result = asyncio.run(
        media_processor_module.process_block(
            idx=1,
            raw_url="https://example.com/fail",
            resolved_url="https://example.com/fail",
            user_context="ctx",
            handler=handler,
            user_link="user-link",
            message=message,
        )
    )

    assert result is False
    assert message.answers == []


def test_load_failed_error_contains_reason_when_enabled(monkeypatch: Any) -> None:
    """
    При `errors_enabled=True` сообщение об ошибке содержит явную причину.
    """
    message = FakeMessage()
    handler = FakeHandler()

    async def fake_errors_enabled(_chat_id: int) -> bool:
        return True

    monkeypatch.setattr(media_processor_module, "get_errors_enabled", fake_errors_enabled)

    result = asyncio.run(
        media_processor_module.process_block(
            idx=1,
            raw_url="https://example.com/fail",
            resolved_url="https://example.com/fail",
            user_context="ctx",
            handler=handler,
            user_link="user-link",
            message=message,
        )
    )

    assert result is False
    assert len(message.answers) == 1
    assert "Причина: ошибка скачивания или извлечения" in message.answers[0]["text"]
