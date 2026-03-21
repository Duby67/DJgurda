# AGENTS

## Purpose

Этот файл описывает локальные правила для слоя `src/middlewares/`.

## Scope

`src/middlewares/` отвечает за:

- middleware behavior верхнего уровня;
- DB core, models и processing-слой;
- чтение и изменение chat settings и статистики.

## Read First

Перед изменениями в этом модуле сначала читать:

1. корневой `AGENTS.md`
2. `ARCHITECTURE.md`
3. `docs/RELIABILITY.md`
4. `docs/exec-plans/tech-debt-tracker.md`
5. конкретные файлы в `src/middlewares/`, связанные с задачей

## Local Invariants

- Middleware не должен менять бизнес-поведение молча при деградации БД без явного решения.
- Chat settings semantics должны оставаться предсказуемыми для текущего чата.
- DB-слой должен сохранять понятные границы между:
  - `core`;
  - `models`;
  - `processing`.
- Любые изменения конкурентного поведения статистики требуют повышенного внимания к atomicity.

## Change Rules

- Не маскировать ошибки БД defaults-поведением без явной причины и наблюдаемости.
- При изменении `bot_enabled.py` нужно учитывать команды управления, которые должны проходить даже при отключенном боте.
- Не смешивать Telegram-facing orchestration с persistence logic внутри middleware/db слоя.
- Если задача по сути превращает `processing/` в новый repository/service contract, это нужно явно документировать.

## Test Guidance

- Изменения в middleware и DB processing обычно требуют целевых unit/integration checks.
- Если изменение влияет на orchestration, нужно смотреть и в `test/bot/processing/`.
- Любой запуск тестов требует явного подтверждения пользователя.

## Escalate When

- меняется схема данных или поведение моделей;
- нужно вводить cache, upsert или другую политику конкурентного доступа;
- изменение затрагивает одновременно middleware, bot orchestration и handlers.

## Read Next

- `src/bot/AGENTS.md`
- `test/AGENTS.md`
