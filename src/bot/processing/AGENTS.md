# AGENTS

## Purpose

Этот файл описывает локальные правила для зоны `src/bot/processing/`.

## Scope

`src/bot/processing/` отвечает за:

- извлечение ссылок;
- multi-link routing;
- orchestration обработки блока;
- sender dispatch;
- тексты ошибок и пользовательские ответы на уровне processing flow.

## Read First

Перед изменениями в этой зоне сначала читать:

1. `src/bot/AGENTS.md`
2. `src/handlers/AGENTS.md`
3. `docs/RELIABILITY.md`
4. конкретные файлы из `src/bot/processing/`, связанные с задачей

## Local Invariants

- `media_router.py` отвечает за orchestration block-by-block и итоговое поведение по исходному сообщению.
- `media_processor.py` отвечает за обработку одного блока и не должен превращаться в новый registry/source-policy слой.
- `senders/` должны выбирать способ отправки по typed result, а не по скрытому знанию о конкретном source.
- Ошибки processing flow должны деградировать ясно для пользователя, без избыточной технической детализации.
- Cleanup runtime-файлов после успешной или неуспешной отправки обязателен.

## High-Risk Areas

- условие удаления исходного сообщения;
- порядок и причины error reply;
- параллелизм и `DOWNLOAD_SEMAPHORE`;
- согласованность `MediaResult` normalization и cleanup;
- поведение при `unsupported`, `failed` и internal exceptions.

## Change Rules

- Не вводить source-specific branching в router/processor без крайней необходимости.
- Если меняется поведение `split_into_blocks`, `resolve_url` usage или block outcomes, нужно явно оценивать regressions в multi-link flow.
- Если меняется логика caption/error generation, нужно учитывать mobile readability и HTML-safety.
- Не переносить DB policy внутрь processing, кроме минимально необходимого orchestration-level чтения/записи.

## Test Guidance

- Основные проверки находятся в `test/bot/processing/`.
- Если изменение затрагивает sender behavior или cleanup, могут понадобиться и `test/handlers/` helper tests.
- Любой запуск тестов требует явного подтверждения пользователя.

## Escalate When

- меняется контракт `MediaResult`, sender registry или content-type dispatch;
- требуется менять semantics unsupported/success/failure на уровне всего runtime;
- нужно затрагивать одновременно `src/bot/processing/`, `src/handlers/` и `src/utils/messages.py`.
