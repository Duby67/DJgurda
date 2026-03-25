# Runtime Pipeline

## Purpose

Этот файл описывает главный runtime path и границы ответственности.

## Flow

1. Telegram update попадает в `src/bot/`.
2. Извлечение ссылок и routing происходят в `src/bot/processing/`.
3. `media_router` делает preflight: вызывает `resolve_url`, затем ищет handler сначала по raw URL, затем по resolved URL.
4. `ServiceManager` делает lookup по уже materialized runtime entries из `HandlerRegistry`.
5. `process_block` запускает handler и нормализует typed `MediaResult`.
6. Sender logic превращает этот результат в Telegram API calls.
7. Статистика и настройки чата сохраняются через DB layer.

## Boundaries

- `src/bot/` владеет orchestration и Telegram-facing behavior.
- `src/handlers/` владеет runtime catalog, lookup layer и source-specific extraction/transformation.
- `src/middlewares/db/` владеет persistence concerns.
- `src/utils/` владеет shared helper logic, а не бизнес-оркестрацией.

## Stable Contracts

- `HandlerRegistry` является source of truth для active runtime composition: sources, priorities, factories и runtime classification metadata.
- `HandlerRegistry` также хранит per-source resilience posture для active runtime: dependency surfaces, timeout/retry expectations и degrade signals.
- `ServiceManager` остается thin lookup-wrapper над runtime entries и не владеет execution orchestration.
- `media_router` владеет preflight policy вокруг raw/resolved URL и передачей выбранного handler-а в `process_block`.
- Выбор sender-а должен определяться content type, а не source-specific branching.
- Состояние включения/выключения бота должно проверяться middleware до основной обработки сообщений.

## Risks To Keep Visible

- внешние API и anti-bot поведение;
- обработка и cleanup runtime-файлов;
- поведение DB-слоя для настроек и статистики;
- edge cases в multi-link orchestration.
