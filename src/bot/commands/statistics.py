"""Модуль `statistics`."""
import logging
import html

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from src.config import STATISTICS_TOP_USERS_LIMIT
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
        stats = await get_chat_stats(message.chat.id, limit=None)
        if not stats:
            await message.answer("В этом чате пока нет статистики.")
            return

        source_totals: dict[str, int] = {}
        for _, _, sources in stats:
            for source, count in sources.items():
                source_totals[source] = source_totals.get(source, 0) + count

        top_source, top_source_count = max(source_totals.items(), key=lambda item: item[1])
        safe_top_source = html.escape(top_source)

        lines = [
            f"{EMOJI_STATISTICS} <b>Статистика активности за все время</b>",
            f"Топ-ресурс: {emoji(top_source)} {safe_top_source} ({top_source_count})\n",
        ]
        for idx, (user_id, total, sources) in enumerate(stats[:STATISTICS_TOP_USERS_LIMIT], start=1):
            medal = MEDALS[idx - 1]

            try:
                chat_member = await message.bot.get_chat_member(message.chat.id, user_id)
                user_name = chat_member.user.full_name or f"ID {user_id}"
            except Exception:
                user_name = f"ID {user_id}"

            safe_user_name = html.escape(user_name)
            user_link = f'<a href="tg://user?id={user_id}">{safe_user_name}</a>'

            line = f"{medal} {user_link}\n"
            sorted_sources = sorted(sources.items(), key=lambda item: item[1], reverse=True)
            for source, count in sorted_sources:
                source_emoji = emoji(source)
                safe_source = html.escape(source)
                line += f"   {source_emoji} {safe_source}: {count}\n"
            line += f"   | <b>ВСЕГО</b>: {total}\n"
            lines.append(line)

        await message.answer("\n".join(lines), parse_mode="HTML")
    except Exception:
        logger.exception("Error in /statistics command for user %d", user_id)
        await message.answer("Произошла ошибка при получении статистики.")
