# AGENTS

## Purpose

Этот файл задает правила для локального database-layer в `src/data/db/`.

## Scope

Папка хранит локальные database artifacts вроде `bot.db`.

## Source Of Truth

- `README.md` в папке human-only.
- Содержимое локальной БД не является источником истины для продукта или архитектуры.
- Source of truth по DB behavior находится в коде и tracked docs.

## Context Rules

- Не читать локальную БД по умолчанию.
- Не использовать содержимое этой папки как замену чтению `src/middlewares/` и связанных contracts.
- Заходить сюда только при задаче про migration, debugging локального state или runtime storage.
