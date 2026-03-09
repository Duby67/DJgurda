# Карта корня репозитория

## Назначение

Этот файл нужен для быстрого ориентирования по верхнему уровню проекта без обхода всего дерева.

## Верхнеуровневые директории

- `.github/`
  - GitHub Actions, AI-контекст и task-файл для AI-агента.
- `deploy/`
  - deploy-артефакты репозитория: `deploy/Dockerfile` и серверный deploy-скрипт.
- `docs/`
  - поддерживаемая проектная документация и обзорные карты.
- `local/`
  - локальные и пользовательские материалы, не являющиеся runtime-кодом.
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
- `deploy/manager.sh`
  - серверный скрипт управления deploy и перезапуском контейнера.
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
- `.dockerignore`
  - исключения при сборке Docker-контекста.
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
