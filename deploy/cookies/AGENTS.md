# AGENTS

## Purpose

Этот файл описывает правила для `deploy/cookies/`.

## Scope

`deploy/cookies/` - это deploy-side staging area для materialized cookie files.

## Source Of Truth

- `README.md` human-only.
- Поведение deploy cookie flow задается:
  - `.github/workflows/deploy-dev.yml`
  - `.github/workflows/deploy-prod.yml`
  - `deploy/manager.sh`
  - `docs/design-docs/deploy-storage-layout.md`

## Context Rules

- Не читать содержимое cookie-файлов как часть обычного агентного контекста.
- Не ожидать, что в git будут реальные cookies.
- Использовать эту папку только когда задача явно касается deploy materialization, sync или server delivery.
