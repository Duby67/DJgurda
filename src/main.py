import shutil
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from src.config import BOT_TOKEN
from src.bot.commands import command_routers
from src.bot.lifespan import on_startup, on_shutdown
from src.bot.processing.media_router import router as media_router
from src.middlewares.bot_enabled import BotEnabledMiddleware
from src.utils.logger import setup_logging 

setup_logging()
logger = logging.getLogger(__name__)

if not shutil.which("ffmpeg"):
    logger.error("FFmpeg не найден. Некоторые функции могут не работать.")

async def main():
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    dp.message.middleware(BotEnabledMiddleware())
    
    for router in command_routers:
        dp.include_router(router)
    dp.include_router(media_router)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())