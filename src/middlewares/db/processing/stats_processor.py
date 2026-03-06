"""
Процессор для работы со статистикой использования.

Содержит функции для обновления и получения статистики по пользователям и источникам.
"""

import logging

from typing import List, Tuple, Dict, Any
from sqlalchemy import select, and_
from sqlalchemy.orm import joinedload

from src.middlewares.db.core import AsyncSessionLocal
from src.middlewares.db.models.stats import Stats
from src.middlewares.db.models.sources import Source

logger = logging.getLogger(__name__)

async def update_stats(chat_id: int, user_id: int, source: str) -> None:
    """
    Обновляет статистику для пользователя в чате.
    
    Создает или увеличивает счетчик для конкретного источника.
    
    Args:
        chat_id: ID чата
        user_id: ID пользователя
        source: Название источника (платформы)
    """
    try:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                # Находим или создаем источник
                source_obj = await session.execute(
                    select(Source).where(Source.name == source)
                )
                source_obj = source_obj.scalar_one_or_none()
                if source_obj is None:
                    source_obj = Source(name=source)
                    session.add(source_obj)
                    await session.flush()  # Получаем ID для новой записи

                # Находим существующую статистику
                stats = await session.execute(
                    select(Stats).where(
                        and_(
                            Stats.chat_id == chat_id,
                            Stats.user_id == user_id,
                            Stats.source_id == source_obj.id
                        )
                    )
                )
                stats = stats.scalar_one_or_none()
                
                # Создаем или обновляем запись
                if stats is None:
                    stats = Stats(
                        chat_id=chat_id,
                        user_id=user_id,
                        source_id=source_obj.id,
                        count=1
                    )
                    session.add(stats)
                    logger.debug(f"Создана запись статистики: chat {chat_id}, user {user_id}, source {source}")
                else:
                    stats.count += 1
                    logger.debug(f"Обновлена статистика: chat {chat_id}, user {user_id}, source {source}")
                    
    except Exception as e:
        logger.exception(f"Ошибка обновления статистики для chat {chat_id}, user {user_id}, source {source}")

async def get_chat_stats(chat_id: int, limit: int = 10) -> List[Tuple[int, int, Dict[str, int]]]:
    """
    Получает статистику по чату.
    
    Args:
        chat_id: ID чата
        limit: Максимальное количество пользователей для возврата
        
    Returns:
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
    except Exception as e:
        logger.exception(f"Ошибка получения статистики для чата {chat_id}")
        return []

    # Агрегируем статистику по пользователям
    user_stats = {}
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
    return stats_list[:limit]
