"""
Процессор для работы со статистикой использования.

Содержит функции для обновления и получения статистики по пользователям и источникам.
"""

from datetime import datetime
import logging

from typing import Dict, List, Tuple

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.orm import joinedload

from src.middlewares.db.core import AsyncSessionLocal
from src.middlewares.db.models.stats import Stats
from src.middlewares.db.models.sources import Source

logger = logging.getLogger(__name__)


async def _get_or_create_source_id(session, source: str) -> int:
    """Возвращает ID источника, создавая строку атомарно при первом использовании."""
    await session.execute(
        sqlite_insert(Source)
        .values(name=source)
        .on_conflict_do_nothing(index_elements=[Source.name])
    )

    result = await session.execute(
        select(Source.id).where(Source.name == source)
    )
    source_id = result.scalar_one_or_none()
    if source_id is None:
        raise RuntimeError(f"Failed to resolve source id for {source!r}")
    return source_id


async def _upsert_stats_row(session, *, chat_id: int, user_id: int, source_id: int) -> None:
    """Атомарно создает или увеличивает счетчик статистики."""
    now = datetime.utcnow()
    insert_stmt = sqlite_insert(Stats).values(
        chat_id=chat_id,
        user_id=user_id,
        source_id=source_id,
        count=1,
        created_at=now,
        updated_at=now,
    )
    upsert_stmt = insert_stmt.on_conflict_do_update(
        index_elements=[Stats.chat_id, Stats.user_id, Stats.source_id],
        set_={
            "count": Stats.count + insert_stmt.excluded.count,
            "updated_at": now,
        },
    )
    await session.execute(upsert_stmt)


async def update_stats(chat_id: int, user_id: int, source: str) -> None:
    """
    Обновляет статистику для пользователя в чате.

    Создает или увеличивает счетчик для конкретного источника.

    Аргументы:
        chat_id: ID чата
        user_id: ID пользователя
        source: Название источника (платформы)
    """
    try:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                source_id = await _get_or_create_source_id(session, source)
                await _upsert_stats_row(
                    session,
                    chat_id=chat_id,
                    user_id=user_id,
                    source_id=source_id,
                )
                logger.debug(
                    "Updated stats atomically: chat %s, user %s, source %s (source_id=%s)",
                    chat_id,
                    user_id,
                    source,
                    source_id,
                )
    except IntegrityError:
        logger.exception(
            "Integrity error while updating stats for chat %s, user %s, source %s",
            chat_id,
            user_id,
            source,
        )
    except OperationalError:
        logger.exception(
            "Operational error while updating stats for chat %s, user %s, source %s",
            chat_id,
            user_id,
            source,
        )
    except SQLAlchemyError:
        logger.exception(
            "Failed to update stats for chat %s, user %s, source %s",
            chat_id,
            user_id,
            source,
        )
    except Exception:
        logger.exception(
            "Unexpected failure while updating stats for chat %s, user %s, source %s",
            chat_id,
            user_id,
            source,
        )


async def get_chat_stats(chat_id: int, limit: int | None = 10) -> List[Tuple[int, int, Dict[str, int]]]:
    """
    Получает статистику по чату.
    
    Аргументы:
        chat_id: ID чата
        limit: Максимальное количество пользователей для возврата.
            Если `None`, возвращает всех пользователей.
        
    Возвращает:
        Список кортежей (user_id, total_count, {source: count})
    """
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Stats)
                .options(joinedload(Stats.source_rel))
                .where(Stats.chat_id == chat_id)
            )
            rows = result.unique().scalars().all()
    except Exception:
        logger.exception(f"Failed to get stats for chat {chat_id}")
        return []

    # Агрегируем статистику по пользователям
    user_stats: dict[int, dict[str, int | dict[str, int]]] = {}
    for stat in rows:
        uid = stat.user_id
        if uid not in user_stats:
            user_stats[uid] = {"total": 0, "sources": {}}
        
        user_stats[uid]["total"] += stat.count
        user_stats[uid]["sources"][stat.source_rel.name] = stat.count

    # Сортируем по общему количеству и ограничиваем результат
    stats_list = [
        (user_id, data["total"], data["sources"])
        for user_id, data in user_stats.items()
    ]
    stats_list.sort(key=lambda x: x[1], reverse=True)
    if limit is None:
        return stats_list
    return stats_list[:limit]
