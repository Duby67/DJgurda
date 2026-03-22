# Swarm Runtime

## Purpose

Этот документ фиксирует runtime-контракты текущего swarm-контура:

- какие артефакты создает run;
- какие role jobs существуют;
- как устроен isolated workspace;
- где проходит граница между local automation и external AI runtime.

Читать его стоит, если задача затрагивает orchestration, MCP front door, job lifecycle или sandbox execution.

## Front Door

Основной пользовательский вход в swarm runtime:

- `python -m scripts.agents.mcp`

Базовые команды:

- `plan_task`
- `start_swarm_run`
- `continue_swarm_run`
- `show_run_status`
- `show_job_queue`
- `show_diff_preview`
- `preview_sandbox_plan`
- `run_dispatcher`
- `run_dispatcher_loop`
- `approve_run_checks`
- `approve_commit`
- `reject_checkpoint`
- `request_commit_approval`
- `request_push_approval`
- `claim_role_job`
- `complete_role_job`
- `fail_role_job`

Эти UX-oriented команды не меняют executor core.
Они работают как поверхностный MCP/CLI слой над уже существующими run artifacts и lifecycle contracts.

## Run Bundle

Каждый run живет в `runs/<run-id>/`.

Базовые артефакты run bundle:

- `input.json`
- `route-result.json`
- `plan.json`
- `context-pack.json`
- `context-trace.json`
- `run-summary.json`
- `approval-checkpoints.json`
- `execution-state.json` после context loading

Дополнительные runtime artifacts появляются по мере прохождения lifecycle:

- `workspace.json`
- `runtime-context-trace.jsonl`
- `loaded-context.json`
- `context-brief.json`
- `context-summary.md`
- `changed-files.json`
- `apply-result.json`
- `verification-plan.json`
- `verification-profile.json`
- `verification-result.json`
- `sandbox-plan.json`
- `sandbox-result.json`
- `review-result.json`
- `approval-request.json`
- `dispatcher-state.json`
- `run-status.md`
- `job-queue.md`
- `diff-preview.md`
- `commit-result.json`
- `push-result.json`
- `close-result.json`

UX layer читает эти артефакты и поверх них строит:

- diff preview через `workspace-diff.patch` или fallback на `changed-files.json`
- sandbox preview через `sandbox-plan.json` или fallback на `verification-plan.json`
- job queue view через `jobs/index.json`

## Role Jobs

Swarm runtime использует фиксированный Phase 3 job order:

1. `planner`
2. `context_loader`
3. `workspace_prepare`
4. `coder`
5. `tester`
6. `sandbox_runner`
7. `reviewer`
8. `release_manager`

Локальные роли:

- `planner`
- `context_loader`
- `workspace_prepare`
- `tester`
- `sandbox_runner`
- `release_manager`

Внешние AI-роли:

- `coder`
- `reviewer`

Каждый job сохраняется как:

- `jobs/index.json`
- `jobs/<job-id>.json`
- `jobs/<job-id>-dispatch.json` после dispatcher handoff
- `jobs/<job-id>-work-item.json` после Codex-style dispatch
- `jobs/<job-id>-result.json` после исполнения

## Job Status Model

Поддерживаемые статусы role jobs:

- `queued`
- `running`
- `completed`
- `failed`
- `blocked`

Отдельно для external jobs ведется dispatch-layer metadata:

- `queued`
- `claimed`
- `dispatched`
- `completed`
- `failed`
- `blocked`

External AI job нельзя завершать напрямую из `queued`:

- сначала `claim_role_job`;
- затем `complete_role_job` или `fail_role_job`.

`run_dispatcher` в текущем UX-слое не является отдельным executor backend.
Это repo-local dispatcher helper, который:

- находит следующий claimable external job;
- при необходимости делает `claim_role_job`;
- пишет dispatch metadata и runtime trace;
- возвращает machine-readable work item для Codex-style runtime handoff.

`run_dispatcher_loop` идет на шаг дальше:

- проверяет completion inbox для уже running external job;
- если находит `jobs/<job-id>-completion.json`, сам завершает job и продолжает orchestration;
- если completion artifact нет, оставляет run в состоянии ожидания внешнего результата;
- если внешних jobs нет, возвращает idle-состояние queue.

## Isolated Workspace

Каждый run получает отдельный workspace в `runs/<run-id>/workspace`.

Стратегии:

- `git_worktree`
  - используется, если исходное дерево чистое;
- `snapshot_copy`
  - используется, если исходное дерево грязное;
  - dirty changes накладываются поверх clean worktree;
  - runtime directories вроде `runs/`, `venv/`, `.pytest_cache/` вычищаются из isolated workspace.

Workspace metadata хранится в `workspace.json`.

## Verification And Sandbox

`tester` не выбирает команды вручную.
Он строит `verification-plan.json` на основе task-specific verification profile.

`sandbox_runner` исполняет этот план через adapter layer:

- `local_dry_run`
  - preview-only adapter;
- `docker`
  - default execution backend, если verification profile требует реальный sandbox;
- `github_actions`
  - explicit remote backend через `dispatch + poll`, не используемый по умолчанию.
  - использует correlation id, workflow artifact download и `swarm-sandbox.yml` как live entrypoint.
  - если в run есть `workspace-diff.patch`, remote workflow пытается воспроизвести exact workspace state через inline git patch перед запуском verification.
  - после первичного correlation match runtime закрепляется на конкретном `workflow_run_id` и дальше поллит уже его detail endpoint.

Build context для sandbox test image хранится в `test/docker/swarm-test/`.
Он не должен смешиваться с live deploy assets из `deploy/`.

Sandbox всегда работает поверх isolated workspace, а не поверх корня репозитория.
Выбор adapter теперь делается в executor core:

- явный `--sandbox-adapter` override всегда имеет приоритет;
- если `verification_profile.sandbox_required_for` непустой, по умолчанию выбирается `docker`;
- если профиль не требует реального sandbox, default остается `local_dry_run`.

`preview_sandbox_plan` не запускает sandbox.
Команда только показывает уже собранный sandbox/verification plan в удобном UX-формате.

Для `github_actions` adapter runtime ожидает:

- доступный `gh` CLI на хосте orchestration;
- настроенную auth-сессию с доступом к workflow dispatch и artifact download;
- workflow `.github/workflows/swarm-sandbox.yml` в целевом репозитории;
- workflow artifacts, которые возвращают machine-readable `sandbox-result.json`.
- при наличии `workspace-diff.patch` runtime передает inline patch payload и ждет подтверждение его применения через `workspace-transfer.json`.

## Approval Boundaries

Swarm runtime не отменяет human approval.

Отдельными checkpoint'ами остаются:

- `run_checks`
- `commit`
- `push`

`continue_swarm_run` полезен после approval или ручного вмешательства, но сам по себе не обходит approval boundaries.

UX wrappers для approval:

- `approve_run_checks`
- `approve_commit`
- `reject_checkpoint`

Они используют тот же lifecycle approval contract, что и низкоуровневая команда approve-stage.

## CLI-First UX Surface

Текущий VSCode/MCP UX специально остается CLI-first.
Вместо отдельной панели или extension UI репозиторий дает тонкие команды и tasks:

- `show_run_status` для общей картины run;
- `show_job_queue` для внешних job handoff;
- `show_diff_preview` для проверки workspace diff перед review/approval;
- `preview_sandbox_plan` для проверки verification/sandbox intent;
- `run_dispatcher` для получения следующего external work item;
- approval wrappers для быстрого approve/reject без ручного редактирования JSON.

Human-readable views пишутся прямо в run bundle:

- `show_run_status --human` -> `run-status.md`
- `show_job_queue --human` -> `job-queue.md`
- `show_diff_preview --human` -> `diff-preview.md`

Runtime context audit trail остается append-only:

- initial route/plan trace живет в `context-trace.json`;
- runtime stage events живут в `runtime-context-trace.jsonl`.

## Source Of Truth

Для runtime-поведения source of truth:

- `scripts/agents/mcp/cli.py`
- `scripts/agents/executor.py`
- `scripts/agents/workspace.py`
- `scripts/agents/sandbox_adapters.py`
- relevant lifecycle scripts in `scripts/agents/lifecycle/`
