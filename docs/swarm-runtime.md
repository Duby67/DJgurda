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
- `request_commit_approval`
- `request_push_approval`
- `claim_role_job`
- `complete_role_job`
- `fail_role_job`

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
- `commit-result.json`
- `push-result.json`
- `close-result.json`

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
- `jobs/<job-id>-result.json` после исполнения

## Job Status Model

Поддерживаемые статусы role jobs:

- `queued`
- `running`
- `completed`
- `failed`
- `blocked`

External AI job нельзя завершать напрямую из `queued`:

- сначала `claim_role_job`;
- затем `complete_role_job` или `fail_role_job`.

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
  - реальный execution backend;
- `github_actions`
  - зарезервирован на будущее.

Sandbox всегда работает поверх isolated workspace, а не поверх корня репозитория.

## Approval Boundaries

Swarm runtime не отменяет human approval.

Отдельными checkpoint'ами остаются:

- `run_checks`
- `commit`
- `push`

`continue_swarm_run` полезен после approval или ручного вмешательства, но сам по себе не обходит approval boundaries.

## Source Of Truth

Для runtime-поведения source of truth:

- `scripts/agents/mcp/cli.py`
- `scripts/agents/executor.py`
- `scripts/agents/workspace.py`
- `scripts/agents/sandbox_adapters.py`
- relevant lifecycle scripts in `scripts/agents/lifecycle/`
