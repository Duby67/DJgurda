# AGENTS

## Purpose

Этот файл описывает локальные правила для smoke и regression checks automation-слоя в `test/scripts/`.

## Scope

`test/scripts/` покрывает:

- smoke-checks для `scripts.agents.*`
- smoke-checks для `scripts.release.*`
- базовые regression tests для module-path CLI

## Change Rules

- Не превращать smoke-checks в тяжелые integration tests без явной необходимости.
- Предпочитать быстрые проверки module entrypoints и стабильных dry-run сценариев.
- Не завязывать smoke-checks на реальный `push`, сетевой доступ или внешние секреты.

## Test Guidance

- Для agent routing достаточно проверять classification output и structure ключевых полей.
- Для release automation предпочтителен dry-run и локальная валидация release sync.
- Smoke-check должен быть достаточно быстрым, чтобы его можно было запускать перед работой со swarm-контуром.

## Approval Reminder

- Любой запуск тестов по-прежнему требует явного подтверждения пользователя.
