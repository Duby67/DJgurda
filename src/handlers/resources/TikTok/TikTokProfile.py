"""
Обработчик профилей TikTok.
"""

import re
import json
import aiohttp
import logging
from typing import Optional, Dict, Any

from src.handlers.mixins import PhotoMixin

logger = logging.getLogger(__name__)

class TikTokProfile(PhotoMixin):
    """
    Миксин для обработки профилей TikTok.
    """
    
    async def _extract_profile_info(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Извлекает информацию о профиле TikTok из HTML страницы.
        
        Args:
            url: URL профиля
            
        Returns:
            Словарь с информацией о профиле или None при ошибке
        """
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=15) as resp:
                    if resp.status != 200:
                        logger.error(f"HTTP {resp.status} при загрузке профиля TikTok")
                        return None
                    html = await resp.text()

            # Ищем JSON с данными профиля
            pattern = r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__" type="application/json">(.*?)</script>'
            match = re.search(pattern, html, re.DOTALL)
            if not match:
                logger.error("Не найден JSON с данными профиля TikTok")
                return None

            data = json.loads(match.group(1))
            
            # Пытаемся извлечь информацию через разные пути
            user_info = data.get("__DEFAULT_SCOPE__", {}).get("webapp.user-detail", {}).get("userInfo", {})
            
            if not user_info:
                # Альтернативный путь
                user_info = data.get("UserModule", {}).get("users", {})
                if user_info and isinstance(user_info, dict):
                    usernames = list(user_info.keys())
                    if not usernames:
                        logger.error("Пустой блок users в UserModule")
                        return None
                    user_info = user_info[usernames[0]]
                else:
                    logger.error("Не удалось извлечь userInfo из JSON")
                    return None

            stats = user_info.get("stats", {})
            user = user_info.get("user", {})

            profile_info = {
                'unique_id': user.get('uniqueId'),
                'nickname': user.get('nickname'),
                'signature': user.get('signature', ''),
                'avatar_url': user.get('avatarLarger') or user.get('avatarMedium') or user.get('avatarThumb'),
                'follower_count': stats.get('followerCount', 0),
                'following_count': stats.get('followingCount', 0),
                'heart_count': stats.get('heartCount', 0),
                'video_count': stats.get('videoCount', 0),
            }
            
            return profile_info

        except Exception as exc:
            logger.exception("Ошибка парсинга профиля TikTok: %s", exc)
            return None

    async def _process_tiktok_profile(
        self,
        url: str,
        context: str,
        resolved_url: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Обрабатывает профиль TikTok.
        
        Args:
            url: URL профиля
            context: Контекст сообщения
            resolved_url: Разрешенный URL
            
        Returns:
            Словарь с информацией о профиле или None при ошибке
        """
        target_url = resolved_url or url
        await self._random_delay()

        # Извлекаем информацию о профиле
        profile_info = await self._extract_profile_info(target_url)
        if not profile_info:
            return None

        # Скачиваем аватар если доступен
        avatar_path = None
        if profile_info.get('avatar_url'):
            avatar_path = self._generate_unique_path(
                profile_info['unique_id'] or "avatar", 
                suffix=".jpg"
            )
            if not await self._download_photo(profile_info['avatar_url'], avatar_path):
                avatar_path = None

        # Формируем текст описания
        lines = []
        
        # Заголовок с именем и ссылкой
        unique_id = profile_info.get("unique_id")
        profile_link = f"https://www.tiktok.com/@{unique_id}" if unique_id else target_url

        if profile_info.get("nickname"):
            lines.append(f'<a href="{profile_link}"><b>{profile_info["nickname"]}</b></a>')
        elif unique_id:
            lines.append(f'<a href="{profile_link}"><b>@{unique_id}</b></a>')
        else:
            lines.append(f'<a href="{profile_link}"><b>TikTok Profile</b></a>')

        # Описание профиля
        if profile_info['signature']:
            signature = profile_info['signature']
            if len(signature) > 200:
                signature = signature[:200] + "…"
            lines.append(f"<i>{signature}</i>")

        # Статистика
        lines.append("")
        lines.append(f"👥 Подписчиков: {profile_info['follower_count']:,}")
        lines.append(f"👤 Подписок: {profile_info['following_count']:,}")
        lines.append(f"❤️ Лайков: {profile_info['heart_count']:,}")
        lines.append(f"🎥 Видео: {profile_info['video_count']:,}")

        caption = "\n".join(lines)

        return {
            'type': 'profile',
            'source_name': 'TikTok',
            'file_path': avatar_path,
            'thumbnail_path': None,
            'title': profile_info.get('nickname') or unique_id or 'unknown',
            'uploader': unique_id or 'unknown',
            'original_url': url,
            'context': context,
            'caption_text': caption,
        }
