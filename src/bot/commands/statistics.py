"""Модуль `statistics`."""
import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from src.middlewares.db import get_chat_stats
from src.utils.Emoji import emoji, EMOJI_FIRSTPLACE, EMOJI_SECONDPLACE, EMOJI_THIRDPLACE, EMOJI_STATISTICS

router = Router()
logger = logging.getLogger(__name__)

MEDALS = [EMOJI_FIRSTPLACE, EMOJI_SECONDPLACE, EMOJI_THIRDPLACE]


@router.message(Command("statistics"))
async def status_command(message: Message) -> None:
    """Функция `status_command`."""
    user = message.from_user
    user_id = user.id if user else 0
    username = user.username if user and user.username else "unknown"
    logger.info(
        "User %d (@%s) called /statistics",
        user_id,
        username,
    )
    try:
        stats = await get_chat_stats(message.chat.id, limit=10)
        if not stats:
            await message.answer("В этом чате пока нет статистики.")
            return

        lines = [f"{EMOJI_STATISTICS} <b>Статистика активности</b>\n"]
        for idx, (user_id, total, sources) in enumerate(stats, start=1):
            medal = MEDALS[idx-1] if idx <= 3 else f"{idx}."

            try:
                chat_member = await message.bot.get_chat_member(message.chat.id, user_id)
                user_name = chat_member.user.full_name or f"ID {user_id}"
            except Exception:
                user_name = f"ID {user_id}"

            line = f"{medal} <b>{user_name}</b>\n"
            for source, count in sources.items():
                source_emoji = emoji(source)
                line += f"   {source_emoji} {count}\n"
            line += f"   <b>Всего:</b> {total}\n"
            lines.append(line)

        await message.answer("\n".join(lines), parse_mode="HTML")
    except Exception:
        logger.exception("Error in /statistics command for user %d", user_id)
        await message.answer("Произошла ошибка при получении статистики.")
