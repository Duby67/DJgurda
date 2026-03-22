# Agent-First Docs Migration

## Goal

Перенести контекст репозитория из нескольких перегруженных файлов в набор небольших и agent-friendly документов.

## Scope

- создать новую структуру документов;
- разложить старый контекст по темам;
- архивировать замененные файлы в `local/`;
- сделать верхнеуровневый reading path коротким и предсказуемым.

## Current Sources Being Migrated

- `README.md`
- `.github/ai-context.md`
- `.github/ai-agent-technical-task.md`
- `docs/documentation-sources.md`
- `docs/repository-root-map.md`
- `docs/deploy_layout.md`
- `docs/improvements.md`
- `local/REFACTORING.md`

## Success Criteria

- агент может найти архитектурный, продуктовый, reliability-, security- и planning-контекст без чтения больших mixed-файлов;
- legacy context files больше не являются основным источником истины;
- у репозитория есть понятный reading order от root policies до module-specific context.
