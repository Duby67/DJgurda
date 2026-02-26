from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from src.config import BOT_VERSION

router = Router()

@router.message(Command("status"))
async def status_command(message: Message):
    bot = message.bot
    start_time = getattr(bot, 'start_time', None)
    if start_time:
        await message.answer(
            f"🤖 Погоняло: Джигурда",
            f"📊 Статья: v{BOT_VERSION}",
            f"🕒 Заход: от {start_time.strftime('%Y-%m-%d %H:%M:%S')}"            
        )
    else:
        await message.answer("Время запуска неизвестно.")