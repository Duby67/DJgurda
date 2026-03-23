# AGENTS

## Purpose

Этот файл задает правила для локального runtime-layer в `src/data/cookies/`.

## Scope

Папка содержит локальные cookie artifacts для runtime и smoke-сценариев.

## Source Of Truth

- `README.md` в папке human-only.
- Сами cookie-файлы не являются source of truth для поведения системы.
- Поведение, использующее cookies, определяется кодом в `src/` и профильными docs.

## Context Rules

- Не читать cookie-файлы как обычный контекст по умолчанию.
- Не использовать эту папку как замену чтению handler code.
- Заходить сюда только если задача явно касается cookies path, smoke setup или runtime storage.
