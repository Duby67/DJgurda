"""Startup notification and dispatcher composition."""

from asyncio import timeout
from importlib.metadata import version

from aiogram import Bot, Dispatcher

from djgurda.chat import create_router


def create_dispatcher(admin_ids: list[int]) -> Dispatcher:
    async def notify_admins(bot: Bot) -> None:
        async with timeout(60):
            await bot.me()
            text = f"Бот запущен\nВерсия: {version('djgurda')}"
            for admin_id in dict.fromkeys(admin_ids):
                await bot.send_message(chat_id=admin_id, text=text)

    dispatcher = Dispatcher()
    dispatcher.startup.register(notify_admins)
    dispatcher.include_router(create_router())
    return dispatcher
