# Agent Context Map

## Purpose

Этот файл задает явную маршрутизацию для agent-first работы и помогает не смешивать:

- application runtime бота;
- swarm automation contour.

## How To Use

Для любой задачи агент должен:

1. определить, затрагивает ли задача application runtime, swarm contour или оба слоя;
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
- swarm-задачи должны быстро переходить в `scripts/AGENTS.md`, `docs/swarm-runtime.md` и `docs/swarm-usage.md`;
- bot runtime-задачи должны быстро переходить в `src/` и профильные product/design docs;
- untracked legacy/archive материалы не использовать как основной источник истины без явного запроса пользователя.

## Task Routing

### Swarm Runtime Orchestration Change

- Read AGENTS:
  - `AGENTS.md`
  - `scripts/AGENTS.md`
- Read Docs:
  - `ARCHITECTURE.md`
  - `docs/swarm-runtime.md`
  - `docs/swarm-usage.md`
  - `docs/commit-policy.md`
- Read Code:
  - `scripts/agents/mcp/`
  - `scripts/agents/lifecycle/`
  - `scripts/agents/executor.py`
- Check Tests:
  - `test/scripts/test_swarm_mcp_smoke.py`
  - `test/scripts/test_swarm_executor_smoke.py`

### Swarm Sandbox Or Remote Execution Change

- Read AGENTS:
  - `AGENTS.md`
  - `scripts/AGENTS.md`
  - `test/docker/AGENTS.md`
- Read Docs:
  - `docs/swarm-runtime.md`
  - `docs/sandbox-execution.md`
  - `docs/testing-policy.md`
- Read Code:
  - `scripts/agents/sandbox_adapters.py`
  - `.github/workflows/swarm-sandbox.yml`
  - `test/docker/swarm-test/`
- Check Tests:
  - `test/scripts/test_swarm_sandbox_adapters.py`

### Swarm Workspace Or Artifact Change

- Read AGENTS:
  - `AGENTS.md`
  - `scripts/AGENTS.md`
- Read Docs:
  - `docs/swarm-runtime.md`
  - `docs/commit-policy.md`
- Read Code:
  - `scripts/agents/workspace.py`
  - `scripts/agents/runtime_trace.py`
  - `scripts/agents/lifecycle/status.py`
  - `scripts/agents/lifecycle/request_approval.py`
- Check Tests:
  - `test/scripts/test_workspace_isolation.py`
  - `test/scripts/test_swarm_cli_smoke.py`

### Swarm Policy Or Planning Change

- Read AGENTS:
  - `AGENTS.md`
  - `scripts/AGENTS.md`
- Read Docs:
  - `docs/swarm-runtime.md`
  - `docs/swarm-usage.md`
  - `docs/agent-task-routing.json`
  - `docs/agent-task-classifier.json`
  - `docs/verification-profiles.json`
  - `docs/exec-plans/tech-debt-tracker.md`
- Read Code:
  - `scripts/agents/routing/`
  - `scripts/agents/knowledge.py`
- Check Tests:
  - `test/scripts/test_swarm_cli_smoke.py`

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
  - `scripts/AGENTS.md`
  - `deploy/AGENTS.md`
  - при test-only container scope `test/docker/AGENTS.md`
- Read Docs:
  - `docs/SECURITY.md`
  - `docs/RELIABILITY.md`
  - `docs/design-docs/deploy-storage-layout.md`
- Read Code:
  - `deploy/`
  - `test/docker/`
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

## Context Expansion Rules

Контекст можно расширять только если:

- task-specific code реально вызывает соседний модуль;
- тестовый сбой указывает на соседнюю подсистему;
- локальный `AGENTS.md` явно отправляет в соседнюю зону;
- задача меняет contract, registry, approval boundary или shared helper.

Не нужно автоматически читать:

- весь `src/`;
- весь `scripts/`;
- весь `test/`;
- untracked legacy/archive материалы;
- unrelated source-папки внутри `src/handlers/resources/`.

## Default Escalation Cases

Агент должен поднимать escalation, если:

- задача начинает менять typed contracts, approval boundaries или artifact schema;
- правка переходит из application runtime в swarm contour или наоборот;
- требуется менять и bot orchestration, и swarm lifecycle в одном инкременте;
- для проверки нужны cookies, secrets, сеть или isolated execution.
