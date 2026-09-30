"""Run the bot with long polling."""

import asyncio
import logging
from contextlib import closing
from pathlib import Path

from aiogram import Bot

from djgurda.bot import create_dispatcher
from djgurda.config import Settings
from djgurda.storage import Storage

READY_FILE = Path("/tmp/djgurda-ready")


async def mark_ready() -> None:
    READY_FILE.touch()


async def run(settings: Settings) -> None:
    READY_FILE.unlink(missing_ok=True)
    try:
        with closing(Storage(settings.database_path)) as storage:
            async with Bot(token=settings.bot_token.get_secret_value()) as bot:
                dispatcher = create_dispatcher(settings.admin_ids, storage)
                dispatcher.startup.register(mark_ready)
                # Skip messages sent while offline.
                await bot.delete_webhook(drop_pending_updates=True)
                await dispatcher.start_polling(bot, close_bot_session=False)
    finally:
        READY_FILE.unlink(missing_ok=True)


def main() -> None:
    READY_FILE.unlink(missing_ok=True)
    settings = Settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(run(settings))


if __name__ == "__main__":
    main()
