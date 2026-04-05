# cookies-session-refresher Docker контур

Образ собирается из `debian:bookworm-slim`, устанавливает
Firefox, geckodriver и зависимости из `requirements-cookies.txt`
в системный Python контейнера.

Контейнер `DJgurda-cookies` запускает
`Xvfb + DBus + Firefox + Selenium + geckodriver` и работает с
примонтированным Firefox-профилем `~/firefox_profile`.

Перед Selenium-стартом контейнер обязательно прогоняет
`prepare_runtime_profile.sh`, который удаляет lock/session/cache и
`*.sqlite-wal`/`*.sqlite-shm` из примонтированного рабочего профиля.

Firefox стартует в облегченном Selenium-режиме:
`page_load_strategy=eager`, без session restore, WebGL/GPU,
тяжелого media decode/autoplay и с отключенными FxA/Sync
путями.

Контур одноразового запуска (`docker compose run --rm`) и
подходит для ручного запуска и cron.
