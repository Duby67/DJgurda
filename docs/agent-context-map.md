# Agent Context Map

## Purpose

Этот файл задает явную маршрутизацию для agent-first работы:

- какой контекст читать для разных типов задач;
- какие `AGENTS.md` являются обязательными;
- какие docs нужны для уточнения контекста;
- какие зоны кода считаются основными;
- какие тесты проверять в первую очередь.

## How To Use

Для любой задачи агент должен:

1. определить тип задачи;
2. собрать минимальный базовый context pack;
3. дочитать task-specific context из этого файла;
4. читать код только в перечисленных основных зонах;
5. расширять контекст только при реальной необходимости.

## Base Context Pack

Для любой нетривиальной задачи сначала читать:

- `AGENTS.md`
- `ARCHITECTURE.md`
- `docs/RELIABILITY.md`
- `docs/SECURITY.md`

Дополнительно:

- `README.md` можно читать как human-facing обзор, но не как source of truth для агента;
- `local/` не использовать как основной источник истины без явного запроса пользователя;
- код в `src/` всегда важнее устаревшего markdown-контекста.

## Task Routing

### Bot Command Change

- Read AGENTS:
  - `AGENTS.md`
  - `src/bot/AGENTS.md`
- Read Docs:
  - `ARCHITECTURE.md`
  - `docs/PRODUCT_SENSE.md`
- Read Code:
  - `src/bot/commands/`
  - `src/middlewares/bot_enabled.py`
  - при необходимости `src/middlewares/db/processing/bot_settings_processor.py`
- Check Tests:
  - целевые bot-level tests, если они есть;
  - при влиянии на chat state смотреть `test/bot/processing/`

### Media Routing Bugfix

- Read AGENTS:
  - `AGENTS.md`
  - `src/bot/AGENTS.md`
  - `src/bot/processing/AGENTS.md`
  - при необходимости `src/handlers/AGENTS.md`
- Read Docs:
  - `ARCHITECTURE.md`
  - `docs/RELIABILITY.md`
  - `docs/design-docs/runtime-pipeline.md`
  - `docs/exec-plans/tech-debt-tracker.md`
- Read Code:
  - `src/bot/processing/media_router.py`
  - `src/bot/processing/media_processor.py`
  - `src/bot/processing/link_extractor.py`
  - `src/utils/messages.py`
- Check Tests:
  - `test/bot/processing/test_media_router_multi_link.py`
  - `test/bot/processing/test_media_processor_errors.py`
  - при изменении cleanup или sender behavior смотреть `test/handlers/test_cleanup_helpers.py`

### Caption Or Error Message Change

- Read AGENTS:
  - `AGENTS.md`
  - `src/bot/processing/AGENTS.md`
- Read Docs:
  - `docs/PRODUCT_SENSE.md`
  - `docs/RELIABILITY.md`
- Read Code:
  - `src/utils/messages.py`
  - `src/bot/processing/media_processor.py`
  - `src/bot/processing/media_router.py`
- Check Tests:
  - `test/bot/processing/test_media_processor_errors.py`
  - при handler-side эффекте смотреть `test/handlers/test_cleanup_helpers.py`

### Stable Source Handler Fix

- Read AGENTS:
  - `AGENTS.md`
  - `src/handlers/AGENTS.md`
  - `src/handlers/resources/AGENTS.md`
  - `test/handlers/AGENTS.md`
- Read Docs:
  - `ARCHITECTURE.md`
  - `docs/RELIABILITY.md`
  - `docs/design-docs/runtime-pipeline.md`
- Read Code:
  - конкретную папку source в `src/handlers/resources/<Source>/`
  - `src/handlers/registry.py`
  - `src/handlers/manager.py` только если задача реально затрагивает registration/selection
- Check Tests:
  - `test/handlers/<Source>/test_<source>_handlers_local.py`
  - helper/unit tests рядом с этим source

### VK Research Or VK Bugfix

- Read AGENTS:
  - `AGENTS.md`
  - `src/handlers/AGENTS.md`
  - `src/handlers/resources/AGENTS.md`
  - `src/handlers/resources/VK/AGENTS.md`
  - `test/handlers/AGENTS.md`
- Read Docs:
  - `docs/RELIABILITY.md`
  - `docs/exec-plans/tech-debt-tracker.md`
- Read Code:
  - `src/handlers/resources/VK/`
  - `src/handlers/registry.py` только если задача касается source status
- Check Tests:
  - `test/handlers/VK/test_vk_handlers_local.py`
  - `test/handlers/VK/VK_urls.py`
- Special Note:
  - не трактовать задачу как обычную stable-runtime stabilization без явного решения пользователя

### DB Settings Or Stats Change

- Read AGENTS:
  - `AGENTS.md`
  - `src/middlewares/AGENTS.md`
  - `src/middlewares/db/AGENTS.md`
  - при влиянии на orchestration `src/bot/AGENTS.md`
- Read Docs:
  - `ARCHITECTURE.md`
  - `docs/RELIABILITY.md`
  - `docs/exec-plans/tech-debt-tracker.md`
- Read Code:
  - `src/middlewares/db/core.py`
  - `src/middlewares/db/models/`
  - `src/middlewares/db/processing/`
  - `src/middlewares/bot_enabled.py`
- Check Tests:
  - целевые DB/unit tests, если они существуют;
  - при влиянии на runtime flow смотреть `test/bot/processing/`

### Runtime Contract Or Registry Change

- Read AGENTS:
  - `AGENTS.md`
  - `src/handlers/AGENTS.md`
  - `src/bot/AGENTS.md`
  - `src/bot/processing/AGENTS.md`
- Read Docs:
  - `ARCHITECTURE.md`
  - `docs/design-docs/runtime-pipeline.md`
  - `docs/RELIABILITY.md`
- Read Code:
  - `src/handlers/contracts.py`
  - `src/handlers/registry.py`
  - `src/handlers/manager.py`
  - `src/bot/processing/media_processor.py`
  - `src/bot/processing/senders/`
- Check Tests:
  - `test/bot/processing/`
  - `test/handlers/test_cleanup_helpers.py`
  - source-specific handler tests для затронутых content types

### Deploy Or Infra Change

- Read AGENTS:
  - `AGENTS.md`
- Read Docs:
  - `docs/SECURITY.md`
  - `docs/RELIABILITY.md`
  - `docs/design-docs/deploy-storage-layout.md`
  - `docs/release_notes.md` при релевантном историческом контексте
- Read Code:
  - `deploy/`
  - `.github/workflows/`
  - `src/config.py`
  - `src/utils/runtime_storage.py`
- Check Tests:
  - ручные или isolated checks по deploy/infrastructure;
  - локальные runtime-sensitive прогоны только по явному approval пользователя

### Docs-Only Change

- Read AGENTS:
  - `AGENTS.md`
- Read Docs:
  - только те tracked docs, которые реально относятся к теме
- Read Code:
  - код читать только для проверки, что документация не расходится с реальным поведением
- Check Tests:
  - тесты обычно не нужны;
  - при описании runtime behavior минимум сверить docs с кодом

### Release Or Versioning Change

- Read AGENTS:
  - `AGENTS.md`
- Read Docs:
  - `docs/release_notes.md`
  - `docs/PLANS.md`
  - `docs/exec-plans/tech-debt-tracker.md`
- Read Code:
  - `src/__init__.py`
  - `scripts/release_versioning.py`
  - `scripts/release_promote.py`
  - `scripts/release_dev.py`
  - `scripts/release_main.py`
  - `scripts/release_sync.py`
  - `.github/workflows/release-promote.yml`
- Check Tests:
  - dry-run `scripts/release_promote.py` / `scripts/release_dev.py` / `scripts/release_main.py` по целевой ветке;
  - при изменении manual promotion flow сверять `.github/workflows/release-promote.yml`;
  - прогон `scripts/release_sync.py` при необходимости;
  - другие проверки только по scope релиза и после approval пользователя

### Test Harness Or Smoke Setup Change

- Read AGENTS:
  - `AGENTS.md`
  - `test/AGENTS.md`
  - `test/handlers/AGENTS.md`
  - при необходимости модульный `AGENTS.md` из `src/`
- Read Docs:
  - `docs/RELIABILITY.md`
  - `docs/SECURITY.md`
- Read Code:
  - `test/handlers/_local_cookie_setup.py`
  - `test/handlers/`
  - релевантные исходные модули в `src/`
- Check Tests:
  - затронутый local smoke path;
  - helper tests рядом с измененными test files

## Context Expansion Rules

Контекст можно расширять только если:

- task-specific code реально вызывает соседний модуль;
- тестовый сбой указывает на соседнюю подсистему;
- локальный `AGENTS.md` явно отправляет в соседнюю зону;
- задача меняет contract, registry или shared helper.

Не нужно автоматически читать:

- весь `src/`;
- весь `test/`;
- архивы в `local/`;
- unrelated source-папки внутри `src/handlers/resources/`.

## Default Escalation Cases

Агент должен поднимать escalation, если:

- задача начинает менять typed contracts или stable runtime list;
- правка переходит из одного source в несколько sources;
- требуется менять и bot orchestration, и DB semantics, и handler behavior в одном инкременте;
- для проверки нужны cookies, secrets, сеть или isolated execution.

## Recommended Next Use

Этот файл должен использоваться как основа для будущего machine-readable routing map, например:

- `docs/agent-context-map.yaml`
- `docs/agent-task-routing.json`
