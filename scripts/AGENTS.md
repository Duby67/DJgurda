# Scripts Overview

## Purpose

Этот файл описывает automation-слой в `scripts/` и помогает быстро выбрать нужную точку входа.

Важно: `scripts/` содержит несколько типов automation, но для daily agent work главным является именно swarm contour.

## Primary Domains

### Swarm Runtime

Это основной automation contour для agent-first orchestration.

- `scripts/config.py`
  - общий `ROOT` и базовая конфигурация automation-слоя
- `scripts/agents/mcp/`
  - repo-local front door для swarm orchestration и VSCode task entrypoints
- `scripts/agents/mcp/dispatcher.py`
  - dispatcher, supervisor и runtime-worker handoff для внешних AI jobs
- `scripts/agents/executor.py`
  - orchestration слой для role jobs, dependency order и handoff между local/external ролями
- `scripts/agents/workspace.py`
  - isolated workspace planning и materialization через `git worktree` или dirty snapshot overlay
- `scripts/agents/sandbox_adapters.py`
  - adapter-based sandbox execution для `local_dry_run`, `docker` и `github_actions`
- `scripts/agents/routing/`
  - классификация задач, сбор context pack, построение run bundle и initial plan
- `scripts/agents/lifecycle/`
  - шаги swarm lifecycle после route/plan: execute, apply, verify, review, approvals, commit, push, close, status

### Release Automation

Это соседний, но отдельный слой automation.
Читать его только если задача действительно связана с promotion или versioning.

- `scripts/release/automation/`
  - promotion между ветками, release sync и manual release flow
- `scripts/release/rules/`
  - правила versioning и parsing release tags

## Run Artifacts

- Все swarm run artifacts живут в корневой папке `runs/`.
- `runs/` считается рабочим artifact-layer, а не source of truth для policy или runtime behavior.
- Содержимое `runs/` должно оставаться вне git, кроме служебных файлов самой папки.

## Routing Scripts

Если задача связана с определением task type, сбором context pack и initial plan:

- `scripts/agents/routing/route.py`
- `scripts/agents/routing/plan.py`
- `scripts/agents/routing/run.py`

## Lifecycle Scripts

Если задача связана с выполнением и сопровождением run bundle:

- `scripts/agents/lifecycle/execute.py`
- `scripts/agents/lifecycle/apply.py`
- `scripts/agents/lifecycle/approve.py`
- `scripts/agents/lifecycle/verify.py`
- `scripts/agents/lifecycle/sandbox.py`
- `scripts/agents/lifecycle/review.py`
- `scripts/agents/lifecycle/request_approval.py`
- `scripts/agents/lifecycle/commit.py`
- `scripts/agents/lifecycle/push.py`
- `scripts/agents/lifecycle/close.py`
- `scripts/agents/lifecycle/status.py`

## Execution Style

Канонический способ запуска swarm automation:

- `python -m scripts.agents.mcp`
- `python -m scripts.agents.routing.route`
- `python -m scripts.agents.routing.run`
- `python -m scripts.agents.lifecycle.status`

Release automation запускать только при реальном release scope:

- `python -m scripts.release.automation.promote`
- `python -m scripts.release.automation.sync`

## Common Commands

Типовые swarm-команды:

- `python -m scripts.agents.mcp plan_task --prompt "..." --path path/to/file --pretty`
- `python -m scripts.agents.mcp start_swarm_run --prompt "..." --pretty`
- `python -m scripts.agents.mcp start_autonomous_swarm_run --prompt "..." --pretty`
- `python -m scripts.agents.mcp start_supervised_swarm_run --prompt "..." --pretty`
- `python -m scripts.agents.mcp continue_swarm_run --run-id <run-id> --pretty`
- `python -m scripts.agents.mcp show_run_status --run-id <run-id> --human`
- `python -m scripts.agents.mcp show_job_queue --run-id <run-id> --human`
- `python -m scripts.agents.mcp show_diff_preview --run-id <run-id> --human`
- `python -m scripts.agents.mcp preview_sandbox_plan --run-id <run-id> --human`
- `python -m scripts.agents.mcp run_dispatcher --run-id <run-id> --pretty`
- `python -m scripts.agents.mcp run_supervisor --run-id <run-id> --pretty`
- `python -m scripts.agents.mcp approve_run_checks_and_continue --run-id <run-id> --pretty`
- `python -m scripts.agents.mcp approve_commit_and_continue --run-id <run-id> --pretty`
- `python -m scripts.agents.mcp approve_push_and_continue --run-id <run-id> --pretty`

Release-команды:

- `python -m scripts.release.automation.promote --source-branch swarm-dev --target-branch dev --target-kind preview --human`
- `python -m scripts.release.automation.promote --source-branch dev --target-branch main --target-kind stable --human`
- `python -m scripts.release.automation.sync --tag v1.2.4`

## Context Rules

- Не читать весь `scripts/` по умолчанию.
- Начинать с нужного домена:
  - `mcp` для пользовательского входа и orchestration-команд
  - `executor` для role jobs, workspace и sandbox handoff
  - `routing` для классификации и подготовки
  - `lifecycle` для выполнения run bundle
  - `release` только для promotion, tag и versioning
- Если задача выглядит как swarm runtime issue, не уходить в `scripts/release/*` без реальной причины.
- При изменении release flow обязательно сверять `.github/workflows/release-promote.yml`.

## Push Rule

- Любой `push` требует отдельного явного подтверждения пользователя, даже если пользователь ранее уже запросил серию git-операций.
- Если `push` упрется в sandbox или сетевые ограничения, запрос на повышение прав нужно делать сразу перед выполнением самого `push`.
