import logging

from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from src.config import MEDALS
from src.middlewares.db import get_chat_stats
from src.bot.processing.emoji import get_emoji

router = Router()
logger = logging.getLogger(__name__)


@router.message(Command("statistics"))
async def status_command(message: Message):
    user = message.from_user
    logger.info(
        "User %d (@%s) called /start",
        user.id, user.username or "unknown"
    )
    try:
        stats = await get_chat_stats(message.chat.id, limit=10)
        if not stats:
            await message.answer("В этом чате пока нет статистики.")
            return

        lines = ["📊 <b>Статистика активности</b>\n"]
        for idx, (user_id, total, sources) in enumerate(stats, start=1):
            medal = MEDALS[idx-1] if idx <= 3 else f"{idx}."

            try:
                chat_member = await message.bot.get_chat_member(message.chat.id, user_id)
                user_name = chat_member.user.full_name or f"ID {user_id}"
            except Exception:
                user_name = f"ID {user_id}"

            line = f"{medal} <b>{user_name}</b>\n"
            for source, count in sources.items():
                emoji = get_emoji(source)
                line += f"   {emoji} {count}\n"
            line += f"   <b>Всего:</b> {total}\n"
            lines.append(line)

        await message.answer("\n".join(lines), parse_mode="HTML")
    except Exception as e:
        logger.exception("Error in /status command for user %d", user.id)
        await message.answer("Произошла ошибка при получении статистики.")