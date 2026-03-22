# Scripts Overview

## Purpose

Этот файл описывает, как устроен automation-слой в `scripts/` и где агенту искать нужную точку входа.

## Layout

- `scripts/config.py`
  - общий `ROOT` и базовая конфигурация automation-слоя
- `scripts/agents/routing/`
  - классификация задач, сбор context pack, построение run bundle и initial plan
- `scripts/agents/lifecycle/`
  - шаги swarm lifecycle после route/plan: execute, apply, verify, review, approvals, commit, push, close, status
- `scripts/release/automation/`
  - promotion между ветками, release sync и manual release flow
- `scripts/release/rules/`
  - правила versioning и parsing release tags

## Run Artifacts

- Все swarm run artifacts живут в корневой папке `runs/`.
- `runs/` считается рабочим artifact-layer, а не source of truth для policy или runtime behavior.
- Содержимое `runs/` должно оставаться вне git, кроме служебных файлов самой папки.

## Routing Scripts

Если задача связана с определением task type и сбором context:

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

## Release Scripts

Если задача связана с promotion или release versioning:

- `scripts/release/automation/promote.py`
- `scripts/release/automation/sync.py`
- `scripts/release/rules/versioning.py`

## Execution Style

После отказа от wrapper-файлов канонический способ запуска Python automation-скриптов такой:

- `python -m scripts.agents.routing.route`
- `python -m scripts.agents.routing.run`
- `python -m scripts.agents.lifecycle.status`
- `python -m scripts.release.automation.promote`
- `python -m scripts.release.automation.sync`

## Common Commands

Типовые команды, которые агент может использовать как отправную точку:

- классификация задачи:
  - `python -m scripts.agents.routing.route --prompt "..." --path path/to/file --pretty`
- сбор run bundle:
  - `python -m scripts.agents.routing.run --prompt "..." --path path/to/file --pretty`
- статус run:
  - `python -m scripts.agents.lifecycle.status --run-id <run-id> --human`
- preview promotion:
  - `python -m scripts.release.automation.promote --source-branch swarm-dev --target-branch dev --target-kind preview --human`
- stable promotion:
  - `python -m scripts.release.automation.promote --source-branch dev --target-branch main --target-kind stable --human`
- release sync:
  - `python -m scripts.release.automation.sync --tag v1.2.4`

## Context Rules

- Не читать весь `scripts/` по умолчанию.
- Начинать с нужного домена:
  - `routing` для классификации и подготовки
  - `lifecycle` для выполнения run bundle
  - `release` для promotion, tag и versioning
- При изменении release flow обязательно сверять `.github/workflows/release-promote.yml`.

## Push Rule

- Любой `push` требует отдельного явного подтверждения пользователя, даже если пользователь ранее уже запросил серию git-операций.
- Если `push` упрется в sandbox или сетевые ограничения, запрос на повышение прав нужно делать сразу перед выполнением самого `push`.
