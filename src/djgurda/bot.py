"""Startup notification and dispatcher composition."""

from importlib.metadata import version

from aiogram import Bot, Dispatcher


def create_dispatcher(admin_ids: list[int]) -> Dispatcher:
    async def notify_admins(bot: Bot) -> None:
        text = f"Бот запущен\nВерсия: {version('djgurda')}"
        for admin_id in dict.fromkeys(admin_ids):
            await bot.send_message(chat_id=admin_id, text=text)

    dispatcher = Dispatcher()
    dispatcher.startup.register(notify_admins)
    return dispatcher
