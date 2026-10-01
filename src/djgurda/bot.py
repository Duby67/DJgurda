"""Administrator notifications and dispatcher composition."""

from asyncio import timeout
from importlib.metadata import version
from pathlib import Path

from aiogram import Bot, Dispatcher

from djgurda import emoji
from djgurda.chat import create_router
from djgurda.storage import Storage


def create_dispatcher(admin_ids: list[int], storage: Storage, work_dir: Path) -> Dispatcher:
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
    dispatcher.startup.register(notify_startup)
    dispatcher.shutdown.register(notify_shutdown)
    dispatcher.include_router(create_router(storage, work_dir))
    return dispatcher
