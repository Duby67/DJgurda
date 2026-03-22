# AGENTS

## Purpose

Этот файл описывает локальные правила для тестового слоя `test/`.

## Scope

`test/` содержит:

- bot-level tests в `test/bot/`;
- handler tests и local smoke scripts в `test/handlers/`.
- test-only container assets в `test/docker/`.

## Read First

Перед изменениями в тестах сначала читать:

1. корневой `AGENTS.md`
2. соответствующий модульный `AGENTS.md` в `src/`
3. конкретные тесты и helper-файлы, которые реально участвуют в задаче

## Local Invariants

- Тесты не являются общим source of truth для архитектуры, но являются источником проверяемого поведения.
- `README.md` в тестовом слое считать human-only документом, а не агентным источником истины.
- Один source smoke-flow должен оставаться локализованным в своей папке `test/handlers/<Source>/`.
- Ссылки и ожидаемые типы для local smoke должны жить в `*_urls.py`, а не хардкодиться в теле smoke-скрипта.
- Cleanup временных файлов после handler smoke checks обязателен.

## Change Rules

- Не переписывать тесты так, чтобы они просто подгонялись под сломанное поведение без осознанного изменения контракта.
- При изменениях в helper-файлах учитывать влияние на все source smoke scripts.
- Для env-зависимых тестов не добавлять скрытые требования к локальной машине без явного описания.

## Test Guidance

- `test/bot/processing/` покрывает bot orchestration и error behavior.
- `test/handlers/` покрывает source behavior, local smoke flows и cleanup helpers.
- Local smoke scripts могут зависеть от cookies, env и внешних сервисов.
- Любой запуск тестов требует явного подтверждения пользователя.

## Escalate When

- тест требует новых секретов, cookies или нестандартной локальной подготовки;
- изменение теста фактически меняет продуктовый или runtime контракт;
- smoke path требует менять общую policy по isolated execution.

## Read Next

- `src/bot/AGENTS.md`
- `src/handlers/AGENTS.md`
- `src/middlewares/AGENTS.md`
- `test/docker/AGENTS.md`
