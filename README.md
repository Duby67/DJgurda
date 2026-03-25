# DJgurda Bot

## О проекте

DJgurda Bot - асинхронный Telegram-бот для обработки медиа-ссылок в чатах.

Пользователь отправляет ссылку на внешний сервис, бот определяет источник, извлекает контент и отправляет результат обратно в чат в удобном формате.

Проект ориентирован в первую очередь на использование в мобильном Telegram-клиенте, поэтому приоритет отдается компактным подписям, понятной подаче результата и устойчивому поведению в обычных чатах.

Дополнительно в репозитории есть отдельный swarm automation contour для agent-first работы с кодовой базой.
Он не заменяет runtime бота, а помогает планировать, исполнять и сопровождать инженерные задачи через run bundle, isolated workspace, sandbox и approval boundaries.

## Что умеет бот

В active runtime бот работает со следующими источниками:

- TikTok
- YouTube
- Instagram
- COUB
- Yandex Music
- VK

`VK` включен в runtime, но остается самым хрупким cookie-sensitive источником и требует более осторожной проверки, чем остальные handlers.

## Для кого этот документ

`README.md` - это обзорный документ для человека:

- чтобы быстро понять, что это за проект;
- чтобы поднять локальную среду;
- чтобы увидеть основные точки входа;
- чтобы понять, где искать более подробную документацию.

Этот файл не является источником истины для агентного контура. Актуальное поведение системы определяется кодом и профильными документами в `docs/`.

Если вас интересует именно swarm contour, смотреть нужно в первую очередь:

- `scripts/AGENTS.md`
- `docs/swarm-runtime.md`
- `docs/swarm-usage.md`

## Как устроен проект

На верхнем уровне:

- `src/` - основной код бота;
- `deploy/` - только live deploy assets для `dev` и `main`;
- `test/docker/` - test-only Docker images для sandbox, smoke и verification;
- `scripts/agents/` - swarm runtime, orchestration, dispatcher, supervisor и sandbox adapters;
- `runs/` - run artifacts swarm-контура;
- `docs/` - поддерживаемая проектная документация;
- `test/` - локальные smoke-проверки и тестовые материалы.

Ключевые части кода:

- `src/main.py` - запуск приложения;
- `src/config.py` - конфигурация через переменные окружения;
- `src/bot/` - маршрутизация сообщений, команды и жизненный цикл;
- `src/handlers/` - обработчики внешних источников;
- `src/middlewares/` - middleware и доступ к данным;
- `src/utils/` - вспомогательные утилиты.

Ключевые части swarm automation:

- `scripts/agents/mcp/cli.py` - основной front door;
- `scripts/agents/mcp/dispatcher.py` - dispatcher и supervisor;
- `scripts/agents/executor.py` - role jobs и orchestration;
- `scripts/agents/workspace.py` - isolated workspace;
- `scripts/agents/sandbox_adapters.py` - sandbox backends.

## Быстрый запуск

### Требования

- Python 3.11+
- FFmpeg в `PATH`

### Установка

```bash
python -m venv venv
# Windows PowerShell
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Если PowerShell блокирует `Activate.ps1` через `ExecutionPolicy`, можно использовать обычный `cmd`:

```bat
venv\Scripts\activate.bat
```

При необходимости dev-инструментов:

```bash
python -m pip install -r requirements-dev.txt
```

### Минимальная настройка

В `.env` должны быть заданы как минимум:

- `BOT_DB_PATH`
- `BOT_VERSION`
- `ADMIN_ID`
- `BOT_TOKEN`
- `YANDEX_MUSIC_TOKEN`

Эталонный пример переменных лежит в `.env.example`.

### Запуск

```bash
python -m src.main
```

### Рекомендуемые настройки VS Code

В репозитории хранится tracked workspace-файл [.vscode/settings.json](/c:/Work/djgurda/.vscode/settings.json) с рекомендуемыми настройками для локальной разработки.

Он:

- направляет Python extension на `venv\Scripts\python.exe`;
- открывает встроенный терминал VS Code с уже активированным `venv` через `activate.bat`;
- согласован с `.vscode/tasks.json`, который тоже ожидает проектный `venv/`.

`python.defaultInterpreterPath` в tracked workspace-настройке задан относительным путем, чтобы VS Code не показывал предупреждение про unresolved variables.
Эта настройка используется как default только при первом выборе интерпретатора для workspace.
Если VS Code уже запомнил другой Python для этого репозитория, нужно один раз выполнить `Python: Select Interpreter` и выбрать `.\venv\Scripts\python.exe`.

## Cookies и локальная среда

Для части источников могут использоваться cookies-файлы.

Общая схема такая:

- `deploy/cookies` - staging-источник для ручных проверок, локальной подготовки и deploy materialization;
- `src/data/cookies` - runtime-копии, с которыми работает приложение.

Контейнерная boundary тоже разделена:

- `deploy/Dockerfile` - реальный deploy image для сервера;
- `test/docker/swarm-test/Dockerfile` - test-only image для swarm verification и smoke.

Если нужны детали по путям, контейнеру и deploy-потоку, смотри профильную документацию, а не этот обзорный файл.

## Команды бота

Основные команды:

- `/help` - список активных источников;
- `/info` - версия и время запуска;
- `/statistics` - статистика активности чата;
- `/start`, `/stop`, `/toggle_bot` - включение и выключение работы бота в текущем чате;
- `/toggle_errors` - управление сообщениями об ошибках;
- `/toggle_notifications` - управление уведомлениями о запуске и остановке.

## Статус проекта

Что важно помнить:

- стабильный контур уже построен вокруг typed runtime boundary;
- `VK` снова включен в active runtime, но остается самым хрупким cookie-sensitive источником;
- локальная среда разработки - Windows 11;
- целевая среда выполнения - Ubuntu 24 в контейнере.

## Swarm Automation

Swarm contour нужен для того, чтобы работать с репозиторием через orchestrated automation:

- классифицировать задачу;
- собирать context pack;
- создавать run bundle;
- материализовать isolated workspace;
- запускать sandbox и review flow;
- доходить до `commit` и `push` только через явные approval boundaries.

Основной вход:

```bash
python -m scripts.agents.mcp
```

Ключевые команды:

- `plan_task`
- `start_swarm_run`
- `start_autonomous_swarm_run`
- `start_supervised_swarm_run`
- `continue_swarm_run`
- `show_run_status`
- `show_job_queue`
- `show_diff_preview`

Подробное использование и ограничения описаны в `docs/swarm-usage.md` и `docs/swarm-runtime.md`.

## Где смотреть детали

Если нужен не обзор, а точная информация по конкретной теме:

- архитектура - `ARCHITECTURE.md`
- проектные принципы - `docs/design-docs/`
- продуктовые ожидания - `docs/product-specs/`
- надежность и ограничения - `docs/RELIABILITY.md`
- безопасность и границы доступа - `docs/SECURITY.md`
- планы и техдолг - `docs/PLANS.md`
- swarm automation usage - `docs/swarm-usage.md`
- swarm runtime contracts - `docs/swarm-runtime.md`
- release flow - `docs/release-flow.md`
- release promote examples - `docs/release-promote-examples.md`
- история релизов - `docs/release_notes.md`

## Замечание для разработчиков

Если документ расходится с кодом, доверять нужно коду и профильным tracked-документам, а не `README.md`.
