# External Dependency Resilience

## Status

- Active.
- Initial planning started on 2026-03-24.
- Current phase: scoped task formation.

## Goal

Усилить resilience внешних зависимостей через per-source metrics, более явные timeout/retry expectations и explicit degrade signals.

## Problem Statement

- Внешние источники и anti-bot behavior остаются важным operational risk.
- Current runtime недостаточно явно формализует per-source timeout/retry/degrade posture.

## Main Areas

- source handlers under `src/handlers/resources/`
- `src/handlers/manager.py`
- `docs/RELIABILITY.md`
- related runtime/degradation tests

## Planned Work

1. Составить карту внешних dependency risks по основным sources.
2. Определить, где нужны per-source metrics и какие signals реально полезны.
3. Зафиксировать timeout/retry/degrade expectations без избыточного scope expansion.
4. Подготовить implementation plan и targeted verification set.
