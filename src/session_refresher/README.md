# session_refresher

Контур автообновления Firefox-сессии для профиля `~/firefox_profile`.

Назначение:

- периодически запускать Firefox через Selenium + geckodriver,
- проходить URL последовательно в одном процессе и одном активном окне Firefox,
- во время жизни страницы выполнять легкие человекоподобные действия (scroll/hover),
- сохранять обновления сессии обратно в профиль,
- писать итоговый `health_verdict` в конце прогона.

Файлы:

- `refresh_session.sh` - оболочка запуска Xvfb/DBus и Python-раннера.
- `refresh_session.py` - основной single-process сценарий Selenium.
- `../../requirements-cookies.txt` - отдельные Python-зависимости контура session-refresher.
