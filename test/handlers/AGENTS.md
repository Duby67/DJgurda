# AGENTS

## Purpose

Этот файл описывает локальные правила для зоны `test/handlers/`.

## Scope

`test/handlers/` содержит:

- source-level local smoke scripts;
- source-specific helper/unit tests;
- общие helper-утилиты вроде `_local_cookie_setup.py` и cleanup checks.

## Read First

Перед изменениями в этой зоне сначала читать:

1. `test/AGENTS.md`
2. `src/handlers/AGENTS.md`
3. `src/handlers/resources/AGENTS.md`
4. конкретную source-папку внутри `test/handlers/`

## Local Invariants

- Одна source-папка должна оставаться самодостаточной для своих smoke paths.
- `*_urls.py` является местом для набора тестовых ссылок и ожидаемых типов.
- `_local_cookie_setup.py` влияет сразу на несколько smoke flows и считается shared high-risk helper.
- Cleanup helpers должны продолжать удалять временные runtime-файлы после прогонов.

## Change Rules

- Не хардкодить тестовые ссылки прямо в smoke-скриптах, если для source уже есть `*_urls.py`.
- Не добавлять новые env/cookies assumptions молча.
- Изменения shared helpers нужно оценивать как cross-source change, а не как локальную правку одного теста.
- Не превращать local smoke scripts в канонический источник архитектурной правды.

## Test Guidance

- `test_<source>_handlers_local.py` используется как полный local smoke path.
- Helper/unit tests рядом с source-файлами нужны для узких regressions и cleanup behavior.
- Любой запуск тестов требует явного подтверждения пользователя.

## Escalate When

- изменение shared helper-а влияет на несколько sources;
- для нового smoke flow нужны новые cookies, secrets или нестандартный local setup;
- тестовая правка фактически меняет runtime contract, а не только проверку.
