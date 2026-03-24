# Chat Settings Read Amplification

## Status

- Active.
- Initial planning started on 2026-03-24.
- Current phase: scoped task formation.

## Goal

Снизить число повторных чтений chat settings и подготовить bounded cache strategy с явной invalidation policy.

## Problem Statement

- Middleware/runtime flow читает chat settings слишком часто.
- Текущая схема может создавать лишнюю нагрузку на DB layer и затруднять predictable degrade semantics.

## Main Areas

- `src/middlewares/bot_enabled.py`
- `src/middlewares/db/processing/bot_settings_processor.py`
- `src/bot/processing/media_router.py`
- `src/bot/processing/media_processor.py`
- related tests in `test/bot/`

## Planned Work

1. Зафиксировать текущие read paths и частоту обращений к settings layer.
2. Определить, где cache действительно нужен, а где создаст лишнюю сложность.
3. Сформировать cache/invalidation contract без размывания source of truth.
4. Подготовить implementation plan и targeted verification set.
