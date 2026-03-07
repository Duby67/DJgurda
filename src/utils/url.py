"""
Утилиты для работы с URL.

Содержит функции для асинхронного разрешения укороченных ссылок
и обработки редиректов.
"""

import asyncio
import logging
from urllib.parse import parse_qs, unquote, urlsplit

import aiohttp

logger = logging.getLogger(__name__)


def _normalize_unwrapped_candidate(candidate: str, fallback_origin: str | None = None) -> str:
    """
    Нормализует кандидата на распаковку из interstitial-ссылки.
    """
    if not isinstance(candidate, str):
        return ""

    decoded = unquote(candidate).strip()
    if not decoded:
        return ""

    if decoded.startswith("//"):
        return f"https:{decoded}"
    if decoded.startswith("/") and fallback_origin:
        return f"{fallback_origin.rstrip('/')}{decoded}"
    return decoded


def _unwrap_interstitial_url(url: str) -> str:
    """
    Распаковывает известные interstitial-URL в исходные ссылки контента.
    """
    parts = urlsplit(url)
    host = parts.netloc.lower()
    query = parse_qs(parts.query)

    candidate_keys = ()
    fallback_origin: str | None = None
    if host == "consent.youtube.com":
        candidate_keys = ("continue", "q", "url")
        fallback_origin = "https://www.youtube.com"
    elif host == "l.instagram.com":
        candidate_keys = ("u", "url")
        fallback_origin = "https://www.instagram.com"

    for key in candidate_keys:
        for raw_candidate in query.get(key, []):
            candidate = _normalize_unwrapped_candidate(
                raw_candidate,
                fallback_origin=fallback_origin,
            )
            if candidate.startswith(("http://", "https://")):
                return candidate

    return url


def _unwrap_interstitial_chain(url: str, max_hops: int = 3) -> str:
    """
    Повторно распаковывает interstitial-цепочку (если есть вложенные редиректы).
    """
    current = url
    for _ in range(max_hops):
        unwrapped = _unwrap_interstitial_url(current)
        if unwrapped == current:
            break
        current = unwrapped
    return current


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
                    final_url = _unwrap_interstitial_chain(str(resp.url))
                    logger.debug(f"URL resolved via HEAD: {initial_url} -> {final_url}")
                    return final_url
                
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                # Если HEAD не сработал, пробуем GET
                logger.debug(f"HEAD failed for {initial_url}: {e}. Trying GET...")
                async with session.get(
                    initial_url, 
                    allow_redirects=True, 
                    timeout=aiohttp.ClientTimeout(total=timeout)
                ) as resp:
                    final_url = _unwrap_interstitial_chain(str(resp.url))
                    logger.debug(f"URL resolved via GET: {initial_url} -> {final_url}")
                    return final_url
                
    except Exception as e:
        logger.warning(f"Failed to resolve final URL {initial_url}: {e}")
        # Возвращаем исходный URL как резервный вариант
        return _unwrap_interstitial_chain(initial_url)
