import re
import json
import asyncio
import aiohttp
import logging
from typing import Optional, Dict, Any

from src.handlers.mixins import PhotoMixin

logger = logging.getLogger(__name__)

class TikTokProfile(PhotoMixin):
    """
    Миксин для обработки профиля TikTok.
    Наследует PhotoMixin для скачивания аватара.
    """
    async def _extract_profile_info(self, url: str) -> Optional[Dict]:
        """
        Загружает страницу профиля и извлекает данные из JSON.
        Возвращает словарь с информацией о профиле.
        """
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=15) as resp:
                    if resp.status != 200:
                        logger.error(f"HTTP {resp.status} при загрузке профиля")
                        return None
                    html = await resp.text()

            # Ищем JSON-данные в скрипте с id="__UNIVERSAL_DATA_FOR_REHYDRATION__"
            # Пример: <script id="__UNIVERSAL_DATA_FOR_REHYDRATION__" type="application/json"> {...} </script>
            pattern = r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__" type="application/json">(.*?)</script>'
            match = re.search(pattern, html, re.DOTALL)
            if not match:
                logger.error("Не найден JSON с данными профиля")
                return None

            data = json.loads(match.group(1))
            # Навигация по структуре JSON (может меняться, нужно адаптировать)
            user_info = data.get("__DEFAULT_SCOPE__", {}).get("webapp.user-detail", {}).get("userInfo", {})
            if not user_info:
                # Альтернативный путь
                user_info = data.get("UserModule", {}).get("users", {})
                # Попробуем извлечь первого пользователя (если словарь)
                if user_info and isinstance(user_info, dict):
                    # Берём первый ключ (ник)
                    username = list(user_info.keys())[0]
                    user_info = user_info[username]
                else:
                    logger.error("Не удалось извлечь userInfo")
                    return None

            stats = user_info.get("stats", {})
            user = user_info.get("user", {})

            profile_info = {
                'unique_id': user.get('uniqueId'),          # @username
                'nickname': user.get('nickname'),
                'signature': user.get('signature', ''),
                'avatar_url': user.get('avatarLarger') or user.get('avatarMedium') or user.get('avatarThumb'),
                'follower_count': stats.get('followerCount', 0),
                'following_count': stats.get('followingCount', 0),
                'heart_count': stats.get('heartCount', 0),
                'video_count': stats.get('videoCount', 0),
            }
            return profile_info

        except Exception as e:
            logger.exception(f"Ошибка парсинга профиля TikTok: {e}")
            return None

    async def _process_tiktok_profile(
        self,
        url: str,
        context: str,
        resolved_url: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Основной метод обработки профиля.
        Скачивает аватар и возвращает словарь для отправки.
        """
        target_url = resolved_url or url
        await self._random_delay()

        # Извлекаем информацию о профиле
        profile_info = await self._extract_profile_info(target_url)
        if not profile_info:
            return None

        # Скачиваем аватар, если есть
        avatar_path = None
        if profile_info.get('avatar_url'):
            # Генерируем уникальное имя для аватара
            avatar_path = self._generate_unique_path(profile_info['unique_id'] or "avatar", suffix=".jpg")
            if not await self._download_photo(profile_info['avatar_url'], avatar_path):
                avatar_path = None  # если не удалось скачать, игнорируем

        # Формируем текст для caption
        lines = []
        if profile_info['nickname']:
            lines.append(f"<b>{profile_info['nickname']}</b>")
        if profile_info['unique_id']:
            lines.append(f"@{profile_info['unique_id']}")
        if profile_info['signature']:
            # Обрезаем слишком длинную подпись
            signature = profile_info['signature'][:200] + "…" if len(profile_info['signature']) > 200 else profile_info['signature']
            lines.append(f"<i>{signature}</i>")
        lines.append("")
        lines.append(f"👥 Подписчиков: {profile_info['follower_count']:,}")
        lines.append(f"👤 Подписок: {profile_info['following_count']:,}")
        lines.append(f"❤️ Лайков: {profile_info['heart_count']:,}")
        lines.append(f"🎥 Видео: {profile_info['video_count']:,}")

        caption = "\n".join(lines)

        return {
            'type': 'profile',
            'source_name': 'TikTok',
            'file_path': avatar_path,      # может быть None
            'thumbnail_path': None,
            'title': profile_info['nickname'],
            'uploader': profile_info['unique_id'],
            'original_url': url,
            'context': context,
            'caption_text': caption,       # готовый текст для отправки
        }