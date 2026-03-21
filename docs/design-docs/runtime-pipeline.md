# Runtime Pipeline

## Purpose

This file describes the main runtime path and ownership boundaries.

## Flow

1. Telegram update enters `src/bot/`.
2. Link extraction and routing happen in `src/bot/processing/`.
3. `resolve_url` normalizes or unwraps the incoming URL.
4. `HandlerRegistry` and `ServiceManager` choose the source handler.
5. The handler produces a typed `MediaResult`.
6. Sender logic converts that result into Telegram API calls.
7. Stats and chat settings are persisted through the DB layer.

## Boundaries

- `src/bot/` owns orchestration and Telegram-facing behavior.
- `src/handlers/` owns source-specific extraction and transformation.
- `src/middlewares/db/` owns persistence concerns.
- `src/utils/` owns shared helper logic, not business orchestration.

## Stable Contracts

- `handler.process()` should produce `MediaResult` for the active runtime flow.
- Sender selection is driven by content type rather than source-specific branching.
- Chat enable/disable state is enforced in middleware before most message handling.

## Risks To Keep Visible

- external APIs and anti-bot behavior;
- runtime file handling and cleanup;
- chat settings and stats DB behavior;
- multi-link orchestration edge cases.
