# URL Extraction And Routing Robustness

## Status

- Active.
- Initial planning started on 2026-03-24.
- Current phase: scoped task formation.

## Goal

Улучшить извлечение URL и routing path так, чтобы снизить false negatives на хвостовой пунктуации и подготовить bounded parallelized `resolve_url` для multi-link batches.

## Problem Statement

- Текущий extraction/routing flow может пропускать валидные URL из-за хвостовой пунктуации.
- Multi-link batches пока не используют более зрелый bounded parallel resolve path.

## Main Areas

- `src/bot/processing/link_extractor.py`
- `src/bot/processing/media_router.py`
- `src/utils/url.py`
- related tests in `test/bot/processing/`

## Planned Work

1. Проверить текущую логику split/extract/resolve на punctuation edge cases.
2. Зафиксировать, где сейчас возможны false negatives и как они проявляются в routing.
3. Оценить, нужен ли bounded parallel `resolve_url` и где проходит безопасная граница конкурентности.
4. Подготовить implementation plan и targeted verification set.
