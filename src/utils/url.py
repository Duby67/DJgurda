"""
Утилиты для работы с URL.

Содержит функции для асинхронного разрешения укороченных ссылок
и обработки редиректов.
"""

import asyncio
import logging

import aiohttp

logger = logging.getLogger(__name__)


async def resolve_url(initial_url: str, timeout: int = 10) -> str:
    """
    Разрешает укороченную ссылку, получая конечный URL.
    
    Сначала пытается использовать HEAD запрос (быстрее),
    если не получается - использует GET запрос.
    
    Аргументы:
        initial_url: Исходная (возможно укороченная) ссылка
        timeout: Таймаут запроса в секундах
        
    Возвращает:
        Конечный URL после всех редиректов или исходный URL при ошибке
    """
    try:
        async with aiohttp.ClientSession() as session:
            try:
                # Пробуем HEAD запрос (быстрее, не загружает тело)
                async with session.head(
                    initial_url, 
                    allow_redirects=True, 
                    timeout=aiohttp.ClientTimeout(total=timeout)
                ) as resp:
                    final_url = str(resp.url)
                    logger.debug(f"URL разрешен через HEAD: {initial_url} -> {final_url}")
                    return final_url
                
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                # Если HEAD не сработал, пробуем GET
                logger.debug(f"HEAD failed for {initial_url}: {e}. Trying GET...")
                async with session.get(
                    initial_url, 
                    allow_redirects=True, 
                    timeout=aiohttp.ClientTimeout(total=timeout)
                ) as resp:
                    final_url = str(resp.url)
                    logger.debug(f"URL разрешен через GET: {initial_url} -> {final_url}")
                    return final_url
                
    except Exception as e:
        logger.warning(f"Ошибка получения полной ссылки {initial_url}: {e}")
        # Возвращаем исходный URL как резервный вариант
        return initial_url
