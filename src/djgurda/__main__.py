"""Run the bot with long polling."""

import asyncio
import logging

from aiogram import Bot

from djgurda.bot import create_dispatcher
from djgurda.config import Settings


async def run(settings: Settings) -> None:
    async with Bot(token=settings.bot_token.get_secret_value()) as bot:
        await create_dispatcher(settings.admin_ids).start_polling(
            bot, close_bot_session=False
        )


def main() -> None:
    settings = Settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(run(settings))


if __name__ == "__main__":
    main()
