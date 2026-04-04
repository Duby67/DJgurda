# session_refresher

Контейнерный контур обновления Firefox-сессии для профиля
`/session_refresher/firefox_profile`.

На хосте этот путь монтируется из
`~/firefox_selenium_profile`, который подготавливается
`~/cookies/runtime/prepare_firefox_profile.sh`.

## Роль этого контура

- `refresh_session.sh` поднимает Xvfb/DBus внутри контейнера,
  проверяет lock профиля и запускает Python-раннер.
- `refresh_session.py` открывает URL в одном Firefox-процессе,
  выполняет легкие human-like действия и обновляет
  `cookies.sqlite` прямо в примонтированном Selenium-профиле.
- `../../requirements-cookies.txt` описывает Python-зависимости,
  которые устанавливаются в системный Python контейнера
  при сборке образа.

## Сценарии запуска

- Ручной запуск внутри контейнера:
  `bash /session_refresher/refresh_session.sh`.
- Ручной запуск контейнера с хоста:
  `~/cookies/runtime/run_session_refresher.sh`.
- Автоматический запуск контейнера:
  cron вызывает тот же
  `~/cookies/runtime/run_session_refresher.sh`.

## Поведение

- Firefox запускается с `page_load_strategy=eager`,
  отключенным session restore, WebGL/GPU и тяжелым
  media decode.
- URL обходятся последовательно в одном процессе и одном
  активном окне Firefox.
- Во время жизни страницы выполняются легкие действия
  `scroll/hover`.
- В конце прогона логируется итоговый
  `health_verdict=healthy|degraded|failed`.
