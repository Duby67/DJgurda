# Testing Policy

## Purpose

Этот документ фиксирует, как swarm-контур выбирает и запускает проверки.

## Core Rules

- Любой запуск тестов, smoke-checks и verification-команд требует явного подтверждения пользователя.
- Для локальных Python-команд, включая `pytest`, smoke-checks и verification-команды, нужно использовать только проектный `venv`.
- Запуск тестов через system `python`, `py` или любой интерпретатор вне проектного `venv` считается нарушением policy.
- Проверки выбираются по принципу target-first:
  - сначала затронутая подсистема;
  - затем соседние проверки только при реальной необходимости;
  - broad repository-wide прогоны не являются default.

## Check Types

- `unit`
  - быстрые локальные проверки из затронутой области;
- `smoke`
  - узкие end-to-end или handler-level проверки для подтверждения базового пути;
- `environment-sensitive`
  - проверки, которым нужны cookies, secrets, сеть, специфичная ОС или внешние сервисы.

## Selection Rules

- Если задача локальна для одной подсистемы, verification должен начинаться с ее целевых checks.
- Если задача меняет contract, registry или shared helper, verification может расширяться на соседние области.
- Если check зависит от env, cookies, secrets или сети, его нужно считать environment-sensitive и выносить в sandbox либо запускать только после отдельного approval.
- Smoke-checks полезны для runtime confidence, но не заменяют policy и code-level reasoning.
- Для каждого `task_type` должен существовать verification profile с:
  - `risk_level`;
  - `required_checks`;
  - `optional_checks`;
  - `allowed_commands`.
- `local_dry_run` не считается реальным execution backend: он подходит для preview orchestration и artifact planning, но не заменяет фактический запуск проверок.
- Для container-based tests, Docker smoke и реального `docker` sandbox execution Docker на хосте обязателен.
- Если Docker недоступен, такие проверки должны честно переходить в `blocked` или `skip`, а не считаться выполненными.
- Real Docker smoke не должен молча зависеть от заранее собранного image: при доступном Docker он должен либо собрать test image, либо честно зафейлиться на build/runtime проблеме.

## Verification Artifact

`verification-result.json` должен по возможности содержать:

- итог `conclusion`;
- краткую `summary`;
- список `checks` с `id`, `status` и заметкой;
- агрегированную `check_summary`;
- ссылки на logs или дополнительные artifacts, если они есть.

## Related Docs

- `docs/RELIABILITY.md`
- `docs/sandbox-execution.md`
- `docs/swarm-usage.md`
- `docs/verification-profiles.json`
