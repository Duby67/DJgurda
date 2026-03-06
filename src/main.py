import shutil
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from src.config import BOT_TOKEN
from src.bot.commands import command_routers
from src.bot.lifespan import on_startup, on_shutdown
from src.bot.processing import media_router
from src.middlewares import BotEnabledMiddleware
from src.utils.logger import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

if not shutil.which("ffmpeg"):
    logger.warning("FFmpeg not found. Some features may not work.")


async def main() -> None:
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    # Регистрируем промежуточный слой для всех сообщений
    dp.message.middleware(BotEnabledMiddleware())
    
    # Включаем роутеры команд
    for router in command_routers:
        dp.include_router(router)
    
    # Включаем медиа-роутер
    dp.include_router(media_router)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
