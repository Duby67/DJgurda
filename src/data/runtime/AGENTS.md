# AGENTS

## Purpose

Этот файл задает правила для временного runtime-layer в `src/data/runtime/`.

## Scope

Папка хранит временные media artifacts и другие локальные runtime outputs.

## Source Of Truth

- `README.md` в папке human-only.
- Runtime artifacts не являются source of truth.
- Контракты и cleanup behavior определяются кодом в `src/`.

## Context Rules

- Не читать runtime files по умолчанию.
- Не использовать временные артефакты как замену чтению handler logic.
- Заходить сюда только если задача явно касается cleanup, temp storage или runtime artifact handling.
