# session_refresher

Контур автообновления Firefox-сессии для профиля `~/firefox_profile`.

Назначение:

- периодически запускать Firefox через Selenium + geckodriver,
- проходить URL последовательно в одном процессе браузера,
- сохранять обновления сессии обратно в профиль.

Файлы:

- `refresh_session.sh` - оболочка запуска Xvfb/DBus и Python-раннера.
- `refresh_session.py` - основной single-process сценарий Selenium.
- `requirements.txt` - Python-зависимости контура session-refresher.
