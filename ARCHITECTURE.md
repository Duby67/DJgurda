# Architecture

## Purpose

Этот файл дает короткую карту репозитория и разделяет два основных рабочих контура:

- application runtime бота;
- swarm automation contour для agent-first orchestration.

## Repository Summary

Репозиторий одновременно содержит:

- асинхронный Telegram-бот для обработки медиа-ссылок;
- automation/runtime слой, через который агент может планировать, запускать и сопровождать swarm-oriented работу по задачам в репозитории.

## Application Runtime

Application runtime живет в `src/`.

Основной пользовательский поток:

`Telegram update -> router -> media_router -> resolve_url -> ServiceManager -> handler.process() -> MediaResult -> sender registry -> Telegram API`

Основные области:

- `src/bot/`
  - Telegram-роутеры, команды, orchestration, startup и shutdown.
- `src/handlers/`
  - registry, source handlers, media services и интеграционная логика.
- `src/middlewares/`
  - chat-state middleware и текущий DB access layer.
- `src/utils/`
  - URL helpers, message formatting, cookies, runtime storage и другие общие утилиты.
- `deploy/`
  - live deploy assets: production/dev bot image, deploy scripts и cookie sync tooling.

## Swarm Automation Contour

Swarm contour живет в `scripts/agents/`, `docs/swarm-runtime.md`, `docs/swarm-usage.md`, `.github/workflows/` и связанных test assets.

Его основной рабочий поток:

`prompt -> route -> plan -> run bundle -> workspace -> local roles -> external roles -> verification/sandbox -> review -> approval boundaries`

Основные области:

- `scripts/agents/routing/`
  - классификация задач, context pack, plan и run bundle bootstrap.
- `scripts/agents/mcp/`
  - front door для swarm orchestration, dispatcher, supervisor и UX wrappers.
- `scripts/agents/lifecycle/`
  - execute/apply/verify/review/approval/commit/push/status stages.
- `scripts/agents/executor.py`
  - role jobs, dependency order и handoff между local/external ролями.
- `scripts/agents/workspace.py`
  - isolated workspace planning и materialization.
- `scripts/agents/sandbox_adapters.py`
  - `local_dry_run`, `docker`, `github_actions`.
- `runs/`
  - run artifacts, а не source of truth.
- `test/scripts/`
  - smoke/regression coverage для swarm contour.
- `test/docker/`
  - test-only container assets для sandbox и smoke.
- `.github/workflows/swarm-sandbox.yml`
  - remote sandbox entrypoint для `github_actions`.

## Key Entrypoints

Application runtime:

- `src/main.py`
- `src/config.py`
- `src/bot/processing/media_router.py`
- `src/handlers/manager.py`
- `src/bot/lifespan/startup.py`
- `src/bot/lifespan/shutdown.py`

Swarm contour:

- `scripts/agents/mcp/cli.py`
- `scripts/agents/mcp/dispatcher.py`
- `scripts/agents/executor.py`
- `scripts/agents/workspace.py`
- `scripts/agents/sandbox_adapters.py`
- `scripts/agents/routing/run.py`

## Shared Constraints

- `README.md` human-facing и не является главным source of truth для агента.
- `runs/` хранит artifacts и не является source of truth для policy или runtime behavior.
- tests не равны source of truth, но остаются важным validation layer.
- Любые тесты и smoke-проверки запускаются только после явного подтверждения пользователя.
- `push`, merge, release и операции с секретами всегда остаются за отдельной approval boundary.

## Swarm-Specific Constraints

- `local_dry_run` - preview-only sandbox adapter.
- `docker` - основной локальный real execution backend для sandbox.
- `github_actions` - remote sandbox backend, а не замена локальному source of truth.
- supervisor и dispatcher снимают ручные швы orchestration, но не обходят approval boundaries.

## Read Next

- `scripts/AGENTS.md` для automation-слоя и точек входа.
- `docs/swarm-runtime.md` для runtime-контрактов swarm-контура.
- `docs/swarm-usage.md` для практического использования swarm automation.
- `docs/RELIABILITY.md`
- `docs/SECURITY.md`
- `docs/PLANS.md`
- `docs/design-docs/index.md` и `docs/product-specs/index.md`, если задача уходит в application runtime.
