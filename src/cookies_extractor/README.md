# cookies_extractor

Контур для извлечения и обновления cookie-файлов.

## Режим запуска

- Только удаленный запуск на сервере (Ubuntu).
- Базовый браузер для извлечения: `firefox`.
- Один запуск обновляет сразу все целевые платформы.

## Папки на хосте

- `~/cookies/YouTube/` - итоговые cookie-файлы YouTube.
- `~/cookies/VK/` - итоговые cookie-файлы VK.
- `~/cookies/Instagram/` - итоговые cookie-файлы Instagram.
- `~/cookies/TikTok/` - итоговые cookie-файлы TikTok.
- `~/cookies/Coub/` - итоговые cookie-файлы Coub.
- `~/firefox_profile/` - Firefox профиль с активными сессиями.

## Скрипты

- `run_extractor.py` - основной orchestration: extract + validate + атомарная замена.
- `extract_youtube_cookies.py` - модуль извлечения cookies по списку доменов.
- `validate_youtube_cookies.py` - модуль валидации cookie-файлов.
- `targets.py` - описание целевых платформ и доменов.
