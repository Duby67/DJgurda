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

## Context Rules

- Не читать весь `scripts/` по умолчанию.
- Начинать с нужного домена:
  - `routing` для классификации и подготовки
  - `lifecycle` для выполнения run bundle
  - `release` для promotion, tag и versioning
- При изменении release flow обязательно сверять `.github/workflows/release-promote.yml`.
