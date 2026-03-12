"""Unit-тесты пакетной обработки ссылок в media_router."""

from __future__ import annotations

import asyncio
import importlib
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

# test/bot/processing/test_media_router_multi_link.py -> project root это parents[3]
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

media_router_module = importlib.import_module("src.bot.processing.media_router")


class FakeHandler:
    """Минимальный handler-объект для тестов роутера."""

    source_name = "FakeSource"


class FakeMessage:
    """Минимальная модель aiogram Message для unit-теста."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.caption = None
        self.chat = SimpleNamespace(id=101)
        self.from_user = SimpleNamespace(id=202, username="tester", full_name="Test User")
        self.message_id = 303
        self.answers: list[dict[str, Any]] = []
        self.deleted = False

    async def answer(self, text: str, reply_parameters: Any = None) -> None:
        self.answers.append(
            {
                "text": text,
                "reply_parameters": reply_parameters,
            }
        )

    async def delete(self) -> None:
        self.deleted = True


def test_delete_original_message_when_all_blocks_success(monkeypatch: Any) -> None:
    """
    Исходное сообщение удаляется, если каждый link-block завершился успешно.
    """
    blocks = [
        ("https://a.example/1", "ctx-a"),
        ("https://a.example/2", "ctx-b"),
    ]
    message = FakeMessage("multi links")
    process_calls: list[str] = []
    handler = FakeHandler()

    class FakeManager:
        def get_handler(self, _url: str) -> FakeHandler:
            return handler

    async def fake_resolve_url(url: str) -> str:
        return url

    async def fake_process_block(*_args: Any, **_kwargs: Any) -> bool:
        process_calls.append(_args[1])
        return True

    async def fake_errors_enabled(_chat_id: int) -> bool:
        return True

    monkeypatch.setattr(media_router_module, "split_into_blocks", lambda _text: blocks)
    monkeypatch.setattr(media_router_module, "get_user_link", lambda _user: "user-link")
    monkeypatch.setattr(media_router_module, "resolve_url", fake_resolve_url)
    monkeypatch.setattr(media_router_module, "process_block", fake_process_block)
    monkeypatch.setattr(media_router_module, "get_errors_enabled", fake_errors_enabled)
    monkeypatch.setattr(media_router_module, "_get_service_manager", lambda: FakeManager())

    asyncio.run(media_router_module.handle_media_message(message))

    assert process_calls == ["https://a.example/1", "https://a.example/2"]
    assert message.deleted is True
    assert message.answers == []


def test_keep_original_message_on_partial_failure(monkeypatch: Any) -> None:
    """
    В mixed-case сообщение не удаляется, но успешные ссылки продолжают обрабатываться.
    """
    blocks = [
        ("https://ok.example/1", "ctx-ok"),
        ("https://fail.example/2", "ctx-fail"),
        ("https://ok.example/3", "ctx-ok-3"),
    ]
    message = FakeMessage("mixed links")
    process_calls: list[str] = []
    handler = FakeHandler()

    class FakeManager:
        def get_handler(self, _url: str) -> FakeHandler:
            return handler

    async def fake_resolve_url(url: str) -> str:
        return url

    async def fake_process_block(_idx: int, raw_url: str, *_args: Any, **_kwargs: Any) -> bool:
        process_calls.append(raw_url)
        return raw_url != "https://fail.example/2"

    async def fake_errors_enabled(_chat_id: int) -> bool:
        return True

    monkeypatch.setattr(media_router_module, "split_into_blocks", lambda _text: blocks)
    monkeypatch.setattr(media_router_module, "get_user_link", lambda _user: "user-link")
    monkeypatch.setattr(media_router_module, "resolve_url", fake_resolve_url)
    monkeypatch.setattr(media_router_module, "process_block", fake_process_block)
    monkeypatch.setattr(media_router_module, "get_errors_enabled", fake_errors_enabled)
    monkeypatch.setattr(media_router_module, "_get_service_manager", lambda: FakeManager())

    asyncio.run(media_router_module.handle_media_message(message))

    assert process_calls == [
        "https://ok.example/1",
        "https://fail.example/2",
        "https://ok.example/3",
    ]
    assert message.deleted is False


def test_unsupported_block_blocks_deletion_and_replies_with_quote(monkeypatch: Any) -> None:
    """
    Unsupported-ссылка должна блокировать удаление и получать отдельный reply с цитатой.
    """
    supported_raw = "https://ok.example/1"
    unsupported_raw = "https://unknown.example/2"
    resolved_map = {
        supported_raw: supported_raw,
        unsupported_raw: "https://resolved.unknown.example/2",
    }
    blocks = [
        (supported_raw, "ctx-ok"),
        (unsupported_raw, "ctx-unsupported"),
    ]
    message = FakeMessage("supported + unsupported")
    process_calls: list[str] = []
    handler = FakeHandler()

    class FakeManager:
        def get_handler(self, url: str) -> FakeHandler | None:
            if url == supported_raw:
                return handler
            return None

    async def fake_resolve_url(url: str) -> str:
        return resolved_map[url]

    async def fake_process_block(_idx: int, raw_url: str, *_args: Any, **_kwargs: Any) -> bool:
        process_calls.append(raw_url)
        return True

    async def fake_errors_enabled(_chat_id: int) -> bool:
        return True

    monkeypatch.setattr(media_router_module, "split_into_blocks", lambda _text: blocks)
    monkeypatch.setattr(media_router_module, "get_user_link", lambda _user: "user-link")
    monkeypatch.setattr(media_router_module, "resolve_url", fake_resolve_url)
    monkeypatch.setattr(media_router_module, "process_block", fake_process_block)
    monkeypatch.setattr(media_router_module, "get_errors_enabled", fake_errors_enabled)
    monkeypatch.setattr(media_router_module, "_get_service_manager", lambda: FakeManager())

    asyncio.run(media_router_module.handle_media_message(message))

    assert process_calls == [supported_raw]
    assert message.deleted is False
    assert len(message.answers) == 1
    assert "Причина: неподдерживаемый источник" in message.answers[0]["text"]
    assert unsupported_raw in message.answers[0]["reply_parameters"].quote


def test_unsupported_error_message_not_sent_when_errors_disabled(monkeypatch: Any) -> None:
    """
    При errors_enabled=False unsupported-ошибка не отправляется в чат.
    """
    unsupported_raw = "https://unknown.example/2"
    blocks = [(unsupported_raw, "ctx-unsupported")]
    message = FakeMessage("unsupported only")

    class FakeManager:
        def get_handler(self, _url: str) -> None:
            return None

    async def fake_resolve_url(url: str) -> str:
        return url

    async def fake_errors_enabled(_chat_id: int) -> bool:
        return False

    monkeypatch.setattr(media_router_module, "split_into_blocks", lambda _text: blocks)
    monkeypatch.setattr(media_router_module, "get_user_link", lambda _user: "user-link")
    monkeypatch.setattr(media_router_module, "resolve_url", fake_resolve_url)
    monkeypatch.setattr(media_router_module, "get_errors_enabled", fake_errors_enabled)
    monkeypatch.setattr(media_router_module, "_get_service_manager", lambda: FakeManager())

    asyncio.run(media_router_module.handle_media_message(message))

    assert message.deleted is False
    assert message.answers == []


def test_multilink_with_requested_urls_keeps_message_on_unsupported(monkeypatch: Any) -> None:
    """
    Сценарий из ТЗ пользователя:
    - unsupported `yandex`;
    - supported `tiktok` и `instagram`.
    Сообщение должно остаться, а unsupported-ссылка должна получить error-reply.
    """
    yandex_url = "https://yandex.ru/search/ASdacad"
    tiktok_url = "https://www.tiktok.com/t/ZP8XA8HA8/"
    instagram_url = "https://www.instagram.com/photo_by_malyshev?igsh=aGg5bHU3eTNjZ2Zk"
    message = FakeMessage("\n".join([yandex_url, tiktok_url, instagram_url]))
    process_calls: list[str] = []
    handler = FakeHandler()

    class FakeManager:
        def get_handler(self, url: str) -> FakeHandler | None:
            if "tiktok.com" in url or "instagram.com" in url:
                return handler
            return None

    async def fake_resolve_url(url: str) -> str:
        return url

    async def fake_process_block(_idx: int, raw_url: str, *_args: Any, **_kwargs: Any) -> bool:
        process_calls.append(raw_url)
        return True

    async def fake_errors_enabled(_chat_id: int) -> bool:
        return True

    monkeypatch.setattr(media_router_module, "get_user_link", lambda _user: "user-link")
    monkeypatch.setattr(media_router_module, "resolve_url", fake_resolve_url)
    monkeypatch.setattr(media_router_module, "process_block", fake_process_block)
    monkeypatch.setattr(media_router_module, "get_errors_enabled", fake_errors_enabled)
    monkeypatch.setattr(media_router_module, "_get_service_manager", lambda: FakeManager())

    asyncio.run(media_router_module.handle_media_message(message))

    assert process_calls == [tiktok_url, instagram_url]
    assert message.deleted is False
    assert len(message.answers) == 1
    assert "Причина: неподдерживаемый источник" in message.answers[0]["text"]
    assert message.answers[0]["reply_parameters"].quote == yandex_url
