# Карта корня репозитория

## Назначение

Этот файл нужен для быстрого ориентирования по верхнему уровню проекта без обхода всего дерева.

## Верхнеуровневые директории

- `.github/`
  - GitHub Actions, AI-контекст и task-файл для AI-агента.
- `deploy/`
  - deploy-артефакты репозитория: `deploy/Dockerfile`, `deploy/Dockerfile.dockerignore`, `deploy/manager.sh`, `deploy/sync_cookies.sh`, `deploy/sync_cookies.bat`, `deploy/sync_cookies.env.example` и `deploy/cookies/.gitkeep`.
- `docs/`
  - поддерживаемая проектная документация и обзорные карты.
- `local/`
  - локальные и пользовательские материалы, не являющиеся runtime-кодом; в `local/cookies` лежат локальные оригиналы cookies для smoke-проверок.
- `scripts/`
  - служебные скрипты проекта, включая release-sync и вспомогательные утилиты.
- `src/`
  - основной runtime-код бота.
- `test/`
  - локальные smoke-скрипты и тестовые материалы для проверки handlers.
- `.vscode/`
  - локальная конфигурация редактора.
- `.pytest_cache/`
  - локальный кеш pytest.
- `venv/`
  - локальное Python-окружение разработки.

## Верхнеуровневые markdown-файлы

- `README.md`
  - главный обзор проекта, запуск, структура и политика актуальности.

## Документы в `docs/`

- `docs/improvements.md`
  - технический backlog, статусы и roadmap улучшений.
- `docs/release_notes.md`
  - журнал заметных изменений по версиям и релизам.
- `docs/deploy_layout.md`
  - схема размещения файлов на сервере и внутри контейнера.
- `docs/documentation-sources.md`
  - карта ролей документов и очередности чтения.
- `docs/repository-root-map.md`
  - этот обзорный файл.

## Deploy-артефакты

- `deploy/Dockerfile`
  - сборка контейнера runtime-окружения.
- `deploy/Dockerfile.dockerignore`
  - docker ignore-файл, привязанный к `deploy/Dockerfile`.
- `deploy/manager.sh`
  - серверный скрипт управления deploy и перезапуском контейнера.
- `deploy/sync_cookies.sh`, `deploy/sync_cookies.bat`
  - ручные скрипты синхронизации cookies на сервер без удаления файлов, которых нет локально.
- `deploy/sync_cookies.env.example`
  - шаблон локального конфига для ручной синхронизации cookies.
- `deploy/cookies/.gitkeep`
  - фиксирует deploy-папку для cookies; реальные `*_cookies.txt` в этой директории не попадают в git.
- `env.example`
  - эталон набора переменных окружения для локальной настройки.
- `requirements.txt`
  - основные Python-зависимости runtime.
- `requirements-dev.txt`
  - дополнительные dev-зависимости.

## Верхнеуровневые служебные конфигурации

- `.gitignore`
  - исключения Git.
- `.gitattributes`
  - правила Git-атрибутов.
- `.markdownlint.json`
  - правила markdownlint.
- `.markdownlintignore`
  - исключения для markdownlint.

## Практический маршрут чтения

1. `README.md`
2. `.github/ai-context.md`
3. `docs/improvements.md`
4. `src/`
5. `docs/deploy_layout.md` и `docs/release_notes.md` по необходимости
