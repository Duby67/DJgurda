from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from src.config import BOT_VERSION
from src.bot.processing.text_utils import get_source_emoji

router = Router()

@router.message(Command("status"))
async def status_command(message: Message):
    bot = message.bot
    start_time = bot.start_time
    if start_time:
        await message.answer(
            f"{get_source_emoji("DJgurda")} Погоняло: DJ гурда\n"
            f"📊 Статья: {BOT_VERSION}\n"
            f"🕒 Заход: от {start_time.strftime('%Y-%m-%d %H:%M:%S')}"
        )
    else:
        await message.answer("Время запуска неизвестно.")