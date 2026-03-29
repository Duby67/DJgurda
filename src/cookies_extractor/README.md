# cookies_extractor

Контур для извлечения и обновления cookie-файлов.

## Режим запуска

- Только удаленный запуск на сервере (Ubuntu).
- Базовый браузер для извлечения: `firefox`.

## Скрипты

- `extract_youtube_cookies.py` - извлекает cookies для `youtube.com` в `/cookies_extractor/cookies/www.youtube.com_cookies.txt`.
- `validate_youtube_cookies.py` - валидирует структуру cookie-файла и домен.
- `run_extractor.py` - выполняет extract + validate + атомарную замену файла.
