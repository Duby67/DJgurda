# Runtime Ownership Of Service Manager

## Status

- Active.
- Initial planning started on 2026-03-24.
- Current phase: scoped task formation.

## Goal

Убрать оставшееся дублирование ownership вокруг `ServiceManager` и сдвинуть runtime к одной application-level модели владения.

## Problem Statement

- Ownership вокруг `ServiceManager` и связанных runtime boundaries все еще описан и, вероятно, реализован не полностью единообразно.
- Это мешает поддерживать четкую application-level модель orchestration ownership.

## Main Areas

- `src/handlers/manager.py`
- `src/handlers/registry.py`
- `src/bot/processing/media_router.py`
- `docs/design-docs/runtime-pipeline.md`
- `ARCHITECTURE.md`

## Planned Work

1. Описать текущую runtime ownership model вокруг `ServiceManager`.
2. Найти оставшиеся дублирующие responsibilities между manager/registry/orchestration layers.
3. Сформировать target ownership model с минимальным scope change.
4. Подготовить implementation plan и targeted verification set.
