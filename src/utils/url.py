"""
Утилиты для работы с URL.

Содержит функции для асинхронного разрешения укороченных ссылок
и обработки редиректов.
"""

import base64
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


def _extract_yandex_retpath_url(url: str) -> str | None:
    """
    Пробует извлечь исходный URL из `retpath` на странице `music.yandex.ru/showcaptcha`.
    """
    parts = urlsplit(url)
    host = parts.netloc.lower()
    if host != "music.yandex.ru" or not parts.path.lower().startswith("/showcaptcha"):
        return None

    query = parse_qs(parts.query)
    for raw_retpath in query.get("retpath", []):
        decoded = unquote(raw_retpath).strip()
        if not decoded:
            continue

        # Yandex добавляет служебный хвост после ",", оставляем только base64-часть.
        b64_candidate = decoded.split(",", 1)[0]
        if not b64_candidate:
            continue

        padding = "=" * (-len(b64_candidate) % 4)
        try:
            unwrapped = base64.urlsafe_b64decode(f"{b64_candidate}{padding}").decode("utf-8").strip()
        except Exception:
            continue

        if unwrapped.startswith(("http://", "https://")):
            return unwrapped
    return None


def _restore_url_from_known_challenges(initial_url: str, final_url: str) -> str:
    """
    Восстанавливает контентный URL для известных anti-bot challenge-редиректов.
    """
    final_parts = urlsplit(final_url)
    if (
        final_parts.netloc.lower() == "music.yandex.ru"
        and final_parts.path.lower().startswith("/showcaptcha")
    ):
        retpath_url = _extract_yandex_retpath_url(final_url)
        if retpath_url:
            return _unwrap_interstitial_chain(retpath_url)
        return _unwrap_interstitial_chain(initial_url)

    return final_url


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
                    final_url = _restore_url_from_known_challenges(initial_url, final_url)
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
                    final_url = _restore_url_from_known_challenges(initial_url, final_url)
                    logger.debug(f"URL resolved via GET: {initial_url} -> {final_url}")
                    return final_url
                
    except Exception as e:
        logger.warning(f"Failed to resolve final URL {initial_url}: {e}")
        # Возвращаем исходный URL как резервный вариант
        return _unwrap_interstitial_chain(initial_url)
