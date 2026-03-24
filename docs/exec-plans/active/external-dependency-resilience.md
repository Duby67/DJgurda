# External Dependency Resilience

## Status

- Active.
- Initial planning started on 2026-03-24.
- Current phase: implementation in progress.

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

## Current Findings

- Stable runtime уже содержит fallback chains и timeout-budget'ы, но они размазаны по source-модулям и shared infrastructure вместо одного registry-level contract.
- `VK` по-прежнему должен оставаться вне stable-runtime resilience contract и не должен выглядеть как обычный stabilization target.
- Наиболее полезный bounded шаг здесь — зафиксировать per-source resilience posture в `HandlerRegistry`, а не пытаться одновременно строить новый metrics subsystem и переписывать все handlers.
- Human-facing docs должны объяснять этот posture, но source of truth для active sources должен остаться в tracked code metadata.
