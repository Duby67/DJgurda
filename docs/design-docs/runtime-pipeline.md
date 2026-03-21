# Runtime Pipeline

## Purpose

Этот файл описывает главный runtime path и границы ответственности.

## Flow

1. Telegram update попадает в `src/bot/`.
2. Извлечение ссылок и routing происходят в `src/bot/processing/`.
3. `resolve_url` нормализует или unwrap-ит входящий URL.
4. `HandlerRegistry` и `ServiceManager` выбирают source handler.
5. Handler производит typed `MediaResult`.
6. Sender logic превращает этот результат в Telegram API calls.
7. Статистика и настройки чата сохраняются через DB layer.

## Boundaries

- `src/bot/` владеет orchestration и Telegram-facing behavior.
- `src/handlers/` владеет source-specific extraction и transformation.
- `src/middlewares/db/` владеет persistence concerns.
- `src/utils/` владеет shared helper logic, а не бизнес-оркестрацией.

## Stable Contracts

- `handler.process()` должен производить `MediaResult` для активного runtime flow.
- Выбор sender-а должен определяться content type, а не source-specific branching.
- Состояние включения/выключения бота должно проверяться middleware до основной обработки сообщений.

## Risks To Keep Visible

- внешние API и anti-bot поведение;
- обработка и cleanup runtime-файлов;
- поведение DB-слоя для настроек и статистики;
- edge cases в multi-link orchestration.
