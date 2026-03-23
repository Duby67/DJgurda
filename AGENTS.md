# AGENTS

## Purpose

Это корневой policy-файл для агентной работы в репозитории.

Репозиторий содержит два рабочих контура:

- application runtime бота в `src/`;
- swarm automation contour в `scripts/agents/`, `docs/swarm-runtime.md` и связанных policy/docs.

Агент должен сначала понять, в каком контуре находится задача, и не смешивать их без необходимости.

## Reading Order

Базовый reading path для любой нетривиальной задачи:

1. `AGENTS.md`
2. `ARCHITECTURE.md`

Если задача затрагивает swarm automation, orchestration, sandbox, approvals, MCP/CLI, run artifacts или VSCode task wrappers, читать дальше в таком порядке:

3. `scripts/AGENTS.md`
4. `docs/swarm-runtime.md`
5. `docs/swarm-usage.md`
6. нужный policy-документ из:
   - `docs/testing-policy.md`
   - `docs/sandbox-execution.md`
   - `docs/commit-policy.md`
   - `docs/SECURITY.md`
7. код и тесты только для затронутой области в `scripts/agents/`, `.github/workflows/`, `test/scripts/`, `test/docker/`

Если задача затрагивает application runtime бота, читать дальше в таком порядке:

3. нужный файл из `docs/product-specs/`
4. нужный файл из `docs/design-docs/`
5. нужный файл из `docs/exec-plans/`
6. код и тесты только для затронутой области в `src/`, `deploy/`, `test/`

## Source Of Truth

- Основной источник истины по поведению application runtime: `src/`.
- Основной источник истины по поведению swarm automation contour:
  - `scripts/agents/`
  - `docs/swarm-runtime.md`
  - связанные tracked policy/docs
- Основной источник истины по правилам работы: tracked-документы, а не архив в `local/`.
- `README.md` считать обзорным human-facing документом, а не source of truth для агента.
- `local/` считать legacy/scratch/archive-слоем, если пользователь явно не попросил опереться на него.
- При расхождении между кодом и устаревшим markdown приоритет у кода.

## Context Loading Rules

- Не читать весь репозиторий по умолчанию.
- Начинать с минимального context pack.
- Расширять контекст только если:
  - зависимость реально пересекает модуль;
  - тест или ошибка указывает на соседнюю область;
  - локальный policy требует прочитать соседний контракт;
  - задача пересекает application runtime и swarm contour.
- Не использовать обзорные и архивные документы как замену чтению целевого кода.
- Не подменять чтение swarm runtime-доков чтением bot-only архитектурных документов, если задача лежит в `scripts/agents/`.

## Change Rules

- Предпочитать локальные изменения внутри одной подсистемы.
- Если изменение пересекает несколько подсистем, явно описывать причину.
- При изменении поведения синхронизировать релевантные docs.
- Если меняется swarm command surface, lifecycle contract, artifact schema или sandbox behavior, синхронизировать:
  - `docs/swarm-runtime.md`
  - `docs/swarm-usage.md`
  - при необходимости `scripts/AGENTS.md`
- Не подключать новые runtime-handlers без явной проверки readiness и env-зависимостей.

## Test And Check Rules

- Любые тесты и smoke-проверки запускать только после явного подтверждения пользователя.
- Для локальных Python-команд, включая `pytest`, smoke-checks и verification-команды, использовать только проектный `venv`.
- Запускать тесты через system `python`, `py` или другой интерпретатор вне проектного `venv` нельзя.
- Environment-sensitive проверки предпочитать в изолированной среде.
- Handler smoke-тесты считать специальным исключением из общего правила, что tests не равны source of truth.
- Для swarm contour учитывать, что:
  - `local_dry_run` не заменяет реальный execution backend;
  - `docker` и `github_actions` являются отдельными sandbox backend'ами со своими ограничениями.

## Approval Rules

- Никогда не предполагать approval на `push`, merge, release или операции с секретами.
- Перед любым `push` всегда отдельно запрашивать явное подтверждение пользователя; если для `push` нужно повышение прав, запрашивать его сразу перед выполнением команды.
- Перед финальным approval показывать измененные файлы, проведенные проверки и остаточные риски.
- Удаленный доступ к серверу остается действием пользователя, а не агента.

## Swarm Default Mode

- По умолчанию агент должен работать в `swarm`-режиме как orchestrator, а не как одиночный исполнитель.
- Для любой нетривиальной задачи агент должен сначала оценить, какие части работы можно безопасно распараллелить, и при необходимости самостоятельно поднимать субагентов без отдельного запроса пользователя.
- Агент может выполнять задачу без субагентов только если шаг тривиальный, узколокальный или находится на критическом пути и делегирование замедлит выполнение.
- Субагентам нужно выдавать четкие и ограниченные зоны ответственности, чтобы не размывать source of truth и не создавать конфликтующие правки.
- Даже в `swarm`-режиме действуют все остальные approval-границы этого репозитория: тесты, smoke checks, `commit`, `push`, release и действия с секретами требуют отдельного подтверждения пользователя.
- Если задача затрагивает несколько подсистем, агент должен предпочитать orchestration через subagents с последующей сборкой итогового решения и явным описанием границ изменений.

## Read Next

- `ARCHITECTURE.md` для общей карты репозитория.
- `scripts/AGENTS.md`, если задача затрагивает automation, swarm lifecycle, sandbox, approvals или release scripts.
- `docs/swarm-runtime.md` для runtime-контрактов swarm-контура.
- `docs/swarm-usage.md` для пользовательских точек входа swarm automation.
- `docs/PRODUCT_SENSE.md` для пользовательских ожиданий application runtime.
- `docs/RELIABILITY.md` для runtime и testing posture.
- `docs/SECURITY.md` для секретов, deploy-boundaries и approval-политики.
- `docs/PLANS.md` для активных и завершенных планов.
