import asyncio
import aiohttp
import logging

from typing import Optional

logger = logging.getLogger(__name__)

async def resolve_url(initial_url: str, timeout: int = 10) -> str:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.head(initial_url, allow_redirects=True, timeout=timeout) as resp:
                return str(resp.url)
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        logger.debug(f"HEAD failed for {initial_url}: {e}. Trying GET...")
        try:
            async with session.get(initial_url, allow_redirects=True, timeout=timeout) as resp:
                return str(resp.url)
        except Exception as e2:
            logger.warning(f"Failed to resolve URL {initial_url}: {e2}")
            return initial_url