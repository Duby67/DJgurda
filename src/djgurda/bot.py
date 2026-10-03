"""Administrator notifications and dispatcher composition."""

import asyncio
from asyncio import timeout
from collections.abc import Awaitable, Callable
from importlib.metadata import version
from pathlib import Path
from typing import Any

from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.types import TelegramObject

from djgurda import emoji
from djgurda.chat import create_router
from djgurda.storage import Storage


class UpdateTasks(BaseMiddleware):
    """Keep handlers alive only while their database and bot session are open."""

    def __init__(self) -> None:
        self.tasks: set[asyncio.Task[Any]] = set()
        self.stopping = False

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if self.stopping:
            return None
        task = asyncio.current_task()
        assert task is not None
        self.tasks.add(task)
        try:
            return await handler(event, data)
        finally:
            self.tasks.discard(task)

    async def shutdown(self) -> None:
        self.stopping = True
        tasks = list(self.tasks - {asyncio.current_task()})
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def create_dispatcher(
    admin_ids: list[int],
    storage: Storage,
    work_dir: Path,
    local_api: bool,
    inline_chat_id: int | None = None,
) -> Dispatcher:
    async def send_to_admins(bot: Bot, text: str) -> None:
        for admin_id in dict.fromkeys(admin_ids):
            await bot.send_message(chat_id=admin_id, text=text, parse_mode="HTML")

    async def notify_startup(bot: Bot) -> None:
        async with timeout(60):
            await bot.me()
            await send_to_admins(
                bot,
                f"{emoji.html('success')} Бот запущен\n"
                f"{emoji.html('version')} Версия: {version('djgurda')}",
            )

    async def notify_shutdown(bot: Bot) -> None:
        async with timeout(10):  # Fits the 30 s stop grace period.
            await send_to_admins(bot, f"{emoji.html('warning')} Бот выключен")

    dispatcher = Dispatcher()
    tasks = UpdateTasks()
    dispatcher.update.outer_middleware(tasks)
    dispatcher.shutdown.register(tasks.shutdown)
    dispatcher.startup.register(notify_startup)
    router = create_router(storage, work_dir, local_api, inline_chat_id)
    # A failed administrator notification must not prevent delivery cleanup.
    router.shutdown.register(notify_shutdown)
    dispatcher.include_router(router)
    return dispatcher
