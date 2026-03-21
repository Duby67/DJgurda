# Tech Debt Tracker

## Purpose

This file is the tracked backlog for open technical debt and unresolved architecture risks.

## Метаданные backlog

- Последняя ревизия backlog: 2026-03-13 | version/tag: v1.2.4

## High Priority

### 1. HTML-safe captions

- Problem:
  - caption assembly still risks invalid HTML if truncation cuts through markup.
- Impact:
  - Telegram send failures on otherwise valid processing results.
- Main area:
  - `src/utils/messages.py`

### 2. DB degradation visibility

- Problem:
  - DB read failures can collapse into silent defaults instead of explicit degradation.
- Impact:
  - production behavior changes without a clear operational signal.
- Main areas:
  - `src/middlewares/bot_enabled.py`
  - `src/middlewares/db/processing/bot_settings_processor.py`

### 3. Atomic stats updates

- Problem:
  - `Source` creation in stats flow is not guaranteed to be atomic under concurrency.
- Impact:
  - race conditions and possible stats loss.
- Main areas:
  - `src/middlewares/db/processing/stats_processor.py`
  - `src/middlewares/db/models/sources.py`

### 4. Docs cleanup after typed-runtime transition

- Problem:
  - parts of the repository still describe outdated legacy boundaries.
- Impact:
  - confusing future changes and agent context selection.
- Main areas:
  - tracked docs
  - selected code comments and docstrings

## Medium Priority

### 5. URL extraction and routing robustness

- Improve URL extraction to avoid punctuation-related false negatives.
- Consider parallelized `resolve_url` with bounded concurrency for multi-link batches.

### 6. Chat settings read amplification

- Current middleware flow reads chat settings too often.
- Introduce a bounded cache and explicit invalidation strategy.

### 7. Runtime ownership of service manager

- Remove duplicate runtime ownership patterns for `ServiceManager`.
- Move toward one application-level ownership model.

### 8. External dependency resilience

- Add per-source metrics, clearer timeout/retry expectations, and explicit degrade signals.
- Keep `VK` on a separate R&D track instead of presenting it as a stabilization task.

## Low Priority

### 9. Helper deduplication

- Extract repeated lightweight helpers only after higher-priority correctness and resilience work.

### 10. Toggle command cleanup

- Reduce repeated toggle flow patterns once more urgent runtime issues are resolved.

## Next Iteration Order

1. HTML-safe captions and routing correctness.
2. DB resilience and atomic stats behavior.
3. Remaining docs cleanup after architecture transition.
4. URL extraction, resolve performance, and chat settings cache.

## Archived Source Notes

- Deeper historical backlog and migration notes now live in `local/legacy-docs/` and `local/REFACTORING.md`.
- Those files are archive input, not the primary tracked backlog.
